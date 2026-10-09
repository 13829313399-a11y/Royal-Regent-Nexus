import base64
import hashlib
from io import BytesIO
from pathlib import Path
import re
import time
from uuid import uuid4
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from app.core.config import settings
from app.models.assistant import AssistantAttachment as Attachment, AssistantMessage as Message
from . import service
from .errors import AssistantError


def path_for(key):
    if not re.fullmatch(r"[a-f0-9]{32}\.png", key):
        raise AssistantError("storage_invalid", "附件记录无效。", 503)
    root = Path(settings.assistant_storage_dir).resolve()
    target = (root / key).resolve()
    if target.parent != root:
        raise AssistantError("storage_invalid", "附件位置无效。", 503)
    return target


def validate_attachments(db, user, sid, ids):
    if len(set(ids)) != len(ids):
        raise AssistantError("attachment_duplicate", "附件重复。")
    rows = []
    for ident in ids:
        row = db.get(Attachment, ident)
        if (not row or row.session_id != sid or row.owner_user_id != user.id or row.employment_epoch != service.epoch(user)
                or (row.expires_at and row.expires_at <= time.time()) or not path_for(row.storage_key).is_file()):
            raise AssistantError("attachment_unavailable", "附件不可用，请重新选择。", 404)
        rows.append(row)
    return rows


def save(user, sid, raw, mime):
    if len(raw) > settings.assistant_max_file_bytes:
        raise AssistantError("attachment_size", "图片超过大小限制。", 413)
    if mime not in ("image/png", "image/jpeg", "image/webp"):
        raise AssistantError("attachment_type", "请选择 PNG、JPEG 或 WebP 静态图片。")
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ("PNG", "JPEG", "WEBP") or Image.MIME.get(image.format) != mime or getattr(image, "is_animated", False):
                raise ValueError()
            if image.width * image.height > 24_000_000:
                raise ValueError()
            image.load()
            width, height = image.size
            out = BytesIO()
            image.convert("RGB").save(out, format="PNG")
            normalized = out.getvalue()  # Strip EXIF/metadata before external transmission.
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise AssistantError("attachment_invalid", "图片无法解码、尺寸过大或类型不匹配。") from None
    if len(normalized) > settings.assistant_max_file_bytes:
        raise AssistantError("attachment_size", "解码后的图片超过大小限制。", 413)
    ident = uuid4().hex
    key = ident + ".png"
    path = path_for(key)
    try:
        with service.transaction() as db:
            service.owned(db, user, sid)
            db.add(Attachment(id=ident, session_id=sid, owner_user_id=user.id, employment_epoch=service.epoch(user),
                storage_key=key, media_type="image/png", byte_size=len(normalized), width=width, height=height,
                sha256=hashlib.sha256(normalized).hexdigest(), created_at=time.time()))
        # Commit the cleanup record before creating a file. A process crash can
        # leave an unavailable attachment, but cannot leave an untracked file.
        with service.transaction() as db:
            service.owned(db, user, sid)
            if not db.get(Attachment, ident):
                raise AssistantError("attachment_unavailable", "对话已移除。", 404)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(normalized)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return dict(id=ident, media_type="image/png", width=width, height=height, byte_size=len(normalized))


def read_verified(row):
    raw = path_for(row.storage_key).read_bytes()
    if len(raw) != row.byte_size or hashlib.sha256(raw).hexdigest() != row.sha256:
        raise AssistantError("attachment_unavailable", "图片保存不完整，请重新上传。", 409)
    return raw


def content(user, ident, *, remove=False):
    with service.transaction() as db:
        row = db.get(Attachment, ident)
        if not row:
            raise AssistantError("not_found", "附件不存在。", 404)
        service.owned(db, user, row.session_id)
        validate_attachments(db, user, row.session_id, [ident])
        if remove:
            for message in db.scalars(select(Message).where(Message.session_id == row.session_id, Message.role == "user")):
                if any(p.get("attachment_id") == ident for p in message.content_parts):
                    raise AssistantError("attachment_referenced", "已发送图片随对话保存，可删除整个对话。", 409)
            path_for(row.storage_key).unlink(missing_ok=True)
            db.delete(row)
            return None
        return read_verified(row)


def data_url(db, user, sid, ident):
    row = validate_attachments(db, user, sid, [ident])[0]
    return "data:" + row.media_type + ";base64," + base64.b64encode(read_verified(row)).decode()
