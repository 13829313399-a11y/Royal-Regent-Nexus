from datetime import timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, BadZipFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from app.core.config import settings
from app.models.collaboration import Attachment, Message
from app.services.identity_resolver import stamp, instant, utc_now
from app.services.transaction_lock import lock_transaction
from .core import identity, conversation, lock_streams, digest, fail, attachment_out

MIME = {".pdf": "application/pdf", ".doc": "application/msword", ".xls": "application/vnd.ms-excel",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def validate(content, filename):
    name = Path(filename.replace("\\", "/")).name
    name = "".join(c for c in name if ord(c) >= 32 and c not in '\r\n')[:240]
    extension = Path(name).suffix.lower()
    mime = MIME.get(extension)
    if not mime or not content:
        fail("UNSUPPORTED_FILE", "仅支持 JPG、PNG、WebP、PDF、Word 和 Excel", 422)
    limit = (15 if mime.startswith("image/") else 25) * 1024 * 1024
    if len(content) > limit:
        fail("FILE_TOO_LARGE", "图片最多 15 MiB，文档最多 25 MiB", 413)
    try:
        if mime.startswith("image/"):
            with Image.open(BytesIO(content)) as img:
                if img.width * img.height > 24_000_000 or Image.MIME.get(img.format) != mime:
                    raise ValueError()
                img.verify()
        elif extension == ".pdf" and not content.startswith(b"%PDF-"):
            raise ValueError()
        elif extension in {".doc", ".xls"} and not content.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            raise ValueError()
        elif extension in {".docx", ".xlsx"}:
            with ZipFile(BytesIO(content)) as archive:
                names = archive.namelist()
                required = "word/document.xml" if extension == ".docx" else "xl/workbook.xml"
                if "[Content_Types].xml" not in names or required not in names or any("vbaproject" in n.lower() for n in names):
                    raise ValueError()
    except (ValueError, OSError, UnidentifiedImageError, BadZipFile, Image.DecompressionBombError):
        fail("INVALID_FILE", "文件内容与格式不符或文件已损坏", 422)
    return name, mime


def path_for(key):
    root = Path(settings.collaboration_storage_dir).resolve()
    path = (root / key).resolve()
    if path.parent != root:
        raise RuntimeError("Invalid private asset storage key")
    return path


def upload(db, user, cid, client_id, filename, mime, content):
    who = identity(user)
    lock_streams(db, [who], cid)
    conversation(db, user, cid)
    request_hash = digest([cid, filename, mime, __import__('hashlib').sha256(content).hexdigest()])
    old = db.scalar(select(Attachment).where(Attachment.owner_id == who[0], Attachment.epoch == who[1], Attachment.client_upload_id == client_id))
    if old:
        if old.request_hash != request_hash:
            fail("UPLOAD_ID_CONFLICT", "同一上传标识对应不同文件")
        if old.state in {"deleting", "deleted"}:
            fail("UPLOAD_EXPIRED", "暂存文件已失效", 410)
        return attachment_out(old)
    aid = uuid4().hex
    path = path_for(aid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    row = Attachment(id=aid, owner_id=who[0], epoch=who[1], client_upload_id=client_id,
        request_hash=request_hash, conversation_id=cid, storage_key=aid, filename=filename, mime=mime,
        size=len(content), state="pending", created_at=stamp())
    try:
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise
    return attachment_out(row)


def readable(db, user, aid):
    row = db.get(Attachment, aid)
    if not row or row.state not in {"pending", "attached"}:
        fail("ATTACHMENT_NOT_FOUND", "附件不存在或不可查看", 404)
    conversation(db, user, row.conversation_id)
    if row.state == "pending":
        if (row.owner_id, row.epoch) != identity(user) or instant(row.created_at) <= utc_now() - timedelta(hours=24):
            fail("ATTACHMENT_NOT_FOUND", "附件不存在或不可查看", 404)
    else:
        message = db.get(Message, row.message_id)
        if message is None or message.retracted_at:
            fail("ATTACHMENT_NOT_FOUND", "附件不存在或不可查看", 404)
    if not path_for(row.storage_key).is_file():
        fail("ATTACHMENT_NOT_FOUND", "附件不存在或不可查看", 404)
    return row


def cancel(db, user, aid):
    lock_streams(db, [identity(user)], assets=[aid])
    row = db.get(Attachment, aid)
    if not row or (row.owner_id, row.epoch) != identity(user):
        fail("ATTACHMENT_NOT_FOUND", "附件不存在或不可查看", 404)
    if row.state == "attached":
        fail("ATTACHMENT_ATTACHED", "已发送的附件须通过撤回消息处理")
    row.state = "deleting"
    db.commit()
    _remove(db, row)
    return {"ok": True}


def _remove(db, row):
    path_for(row.storage_key).unlink(missing_ok=True)
    row.state = "deleted"
    db.commit()


def cleanup(db):
    cutoff = stamp(utc_now() - timedelta(hours=24))
    ids = list(db.scalars(select(Attachment.id).where(
        ((Attachment.state == "pending") & (Attachment.created_at < cutoff)) | (Attachment.state == "deleting")).limit(500)))
    db.rollback()
    removed = 0
    for aid in ids:
        lock_transaction(db, "collab-asset", aid)
        row = db.get(Attachment, aid)
        if row is None or row.state == "attached" or row.state == "deleted":
            db.rollback()
            continue
        if row.state == "pending" and row.created_at >= cutoff:
            db.rollback()
            continue
        row.state = "deleting"
        db.commit()
        _remove(db, row)
        removed += 1
    return {"removed": removed}
