"""Scoped feedback workflow. Canonical IAM checks apply in every rollout mode."""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import PurePosixPath
from uuid import uuid4
import warnings
from zipfile import ZipFile

from fastapi import HTTPException
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.customer_order_ledger import OrderLedgerLine
from app.models.module_feedback import FeedbackAttachment, FeedbackMessage, FeedbackReadReceipt, FeedbackTicket
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext, authorization_decision, can


MODULE = "customer-order-center"
MANAGE = "module_feedback:manage"
SUBMIT = "module_feedback:submit"
MAX_FILES = 5
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_TOTAL_BYTES + 256 * 1024
MATERIALS = ["screenshot", "steps", "expected_result", "original_file", "order_reference"]
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
        ".pdf": "application/pdf", ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _id():
    return str(uuid4())


def _local_scope(user):
    # Feedback is never an implicit extension of a position's cross-factory
    # read scope. A factory binding or explicit wildcard is required here.
    return replace(user, grants=tuple(replace(grant, scope_mode="own_factory", unrestricted_department=False)
                                     for grant in user.grants))


def _can_submit(user, factory_id):
    profile = user.profile
    if not profile or profile.confirmation_status != "confirmed" or profile.primary_factory_id != factory_id:
        return False
    # Confirmed employees have a private feedback channel even without a role
    # or business permission (including when reporting missing access). The
    # canonical catalog and overrides can independently disable that channel.
    # An explicit allow or wildcard administrator never expands the home factory.
    allowed, source, _, _ = authorization_decision(user, SUBMIT, factory_id, profile.primary_department or None)
    return allowed or source == "default"


def _can_link_order(user, factory_id):
    # Keep canonical within-factory position/department semantics (e.g. a
    # general manager's business read), while removing cross-factory expansion.
    local = replace(user, grants=tuple(
        replace(grant, scope_mode="own_factory", read_permissions=frozenset())
        for grant in user.grants if grant.factory_id in {factory_id, "*"}
    ))
    return can(local, "customer_order:read", factory_id, "sales-business")


def capabilities(user: AuthContext, factory_id: str, module: str):
    if factory_id not in ALLOWED_FACTORY_IDS or module != MODULE:
        raise HTTPException(422, "请选择支持的厂区及功能模块")
    scoped = _local_scope(user)
    return {"can_submit": _can_submit(scoped, factory_id),
            "can_link_order": _can_link_order(user, factory_id),
            "can_manage": can(scoped, MANAGE, factory_id, "system"),
            "max_files": MAX_FILES, "max_file_bytes": MAX_FILE_BYTES, "max_total_bytes": MAX_TOTAL_BYTES,
            "allowed_extensions": list(MIME), "material_options": MATERIALS}


def require_submit(user, factory_id, module=MODULE):
    caps = capabilities(user, factory_id, module)
    if not caps["can_submit"]:
        raise HTTPException(403, "未获本厂客户订单反馈权限")
    return caps


def ticket_for_user(db, user, ticket_id, factory_id):
    caps = capabilities(user, factory_id, MODULE)
    if not (caps["can_submit"] or caps["can_manage"]):
        raise HTTPException(403, "未获本厂反馈权限")
    stmt = select(FeedbackTicket).where(FeedbackTicket.id == ticket_id, FeedbackTicket.factory_id == factory_id,
                                        FeedbackTicket.module == MODULE)
    if not caps["can_manage"]:
        stmt = stmt.where(FeedbackTicket.author_id == user.id)
    ticket = db.scalar(stmt)
    if ticket is None:
        raise HTTPException(404, "反馈不存在或无权查看")
    return ticket, caps


@dataclass(frozen=True)
class UploadedFile:
    file_name: str
    content_type: str
    content: bytes
    sha256: str


def validate_uploads(raw_files):
    if len(raw_files) > MAX_FILES or sum(len(content) for _, content in raw_files) > MAX_TOTAL_BYTES:
        raise HTTPException(413, "每次最多5个附件，合计不能超过25MB")
    result = []
    for name, content in raw_files:
        name = (name or "").replace("\\", "/").split("/")[-1]
        if not name or len(name) > 180 or any(ord(c) < 32 for c in name):
            raise HTTPException(422, "附件文件名无效")
        suffix = PurePosixPath(name).suffix.lower()
        if suffix not in MIME:
            raise HTTPException(422, "附件仅支持 JPG、PNG、WebP、PDF、XLS、XLSX")
        if not content or len(content) > MAX_FILE_BYTES:
            raise HTTPException(413, "单个附件须为1字节至10MB")
        try:
            if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(BytesIO(content)) as picture:
                        expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP"}[suffix]
                        if picture.format != expected or picture.width * picture.height > 24_000_000 or getattr(picture, "n_frames", 1) != 1:
                            raise ValueError("invalid image dimensions/format")
                        picture.verify()
                    with Image.open(BytesIO(content)) as picture:
                        picture.load()
            elif suffix == ".pdf":
                # No rendering or content execution: originals are download-only.
                from pypdf import PdfReader
                if not content.startswith(b"%PDF-"):
                    raise ValueError("invalid PDF signature")
                reader = PdfReader(BytesIO(content), strict=True)
                if reader.is_encrypted or not 1 <= len(reader.pages) <= 500:
                    raise ValueError("invalid PDF")
            elif suffix == ".xlsx":
                with ZipFile(BytesIO(content)) as archive:
                    entries = archive.infolist()
                    names = {item.filename for item in entries}
                    if len(entries) > 10000 or sum(item.file_size for item in entries) > 100 * 1024 * 1024:
                        raise ValueError("oversized workbook")
                    if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names):
                        raise ValueError("not a workbook")
                    if any("vbaproject" in n.lower() or n.startswith("xl/embeddings/") for n in names):
                        raise ValueError("active workbook content")
            else:
                import xlrd
                if not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
                    raise ValueError("not an XLS workbook")
                book = xlrd.open_workbook(file_contents=content, on_demand=True)
                book.release_resources()
        except Exception as exc:
            raise HTTPException(422, f"附件格式无效或超过安全限制：{name}") from exc
        result.append(UploadedFile(name, MIME[suffix], content, sha256(content).hexdigest()))
    return result


def _request_hash(payload, uploads):
    data = {"payload": payload.model_dump(), "files": [
        {"name": f.file_name, "sha256": f.sha256} for f in uploads]}
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _check_retry(row, fingerprint):
    if row.request_hash != fingerprint:
        raise HTTPException(409, "重试编号已用于不同内容，请刷新后重试")


def _add_message(db, ticket, user, body, action, kind, request_id, fingerprint, uploads,
                 requested=(), provided=(), release_note=""):
    message = FeedbackMessage(id=_id(), ticket_id=ticket.id, actor_id=user.id, actor_name=user.display_name or user.username,
        actor_kind=kind, body=body, action=action, requested_materials=list(requested), provided_materials=list(provided),
        release_note=release_note, revision=ticket.revision, client_request_id=request_id, request_hash=fingerprint,
        created_at=ticket.updated_at)
    db.add(message)
    db.flush()
    for upload in uploads:
        db.add(FeedbackAttachment(id=_id(), message_id=message.id, file_name=upload.file_name,
            content_type=upload.content_type, size=len(upload.content), sha256=upload.sha256, content=upload.content))


def _mark_read(db, user, ticket, revision):
    db.add(FeedbackReadReceipt(id=_id(), ticket_id=ticket.id, user_id=user.id, through_revision=revision, created_at=_now()))


def _read_revision(db, user, ticket):
    return db.scalar(select(func.max(FeedbackReadReceipt.through_revision)).where(
        FeedbackReadReceipt.ticket_id == ticket.id, FeedbackReadReceipt.user_id == user.id)) or 0


def _unread_clause(user):
    read_revision = select(func.max(FeedbackReadReceipt.through_revision)).where(
        FeedbackReadReceipt.ticket_id == FeedbackTicket.id, FeedbackReadReceipt.user_id == user.id
    ).correlate(FeedbackTicket).scalar_subquery()
    return select(FeedbackMessage.id).where(FeedbackMessage.ticket_id == FeedbackTicket.id,
        FeedbackMessage.actor_id != user.id, FeedbackMessage.revision > func.coalesce(read_revision, 0)
    ).correlate(FeedbackTicket).exists()


def _summary(db, user, ticket, unread=None):
    if unread is None:
        unread = bool(db.scalar(select(_unread_clause(user)).where(FeedbackTicket.id == ticket.id)))
    result = {key: getattr(ticket, key) for key in (
        "id", "factory_id", "module", "title", "category", "emoji", "status", "author_id", "author_name",
        "assigned_name", "context", "requested_materials", "provided_materials", "release_note", "revision", "created_at", "updated_at"
    )} | {"unread": unread}
    caps = capabilities(user, ticket.factory_id, ticket.module)
    if ticket.context.get("order_id") and not (caps["can_link_order"] or caps["can_manage"]):
        # Retain immutable stored evidence, but do not return a previously
        # derived order snapshot after the author's order access is revoked.
        result["context"] = {**ticket.context, "order_id": "", "order_reference": "", "product_no": "", "customer_code": ""}
    return result


def detail(db, user, ticket_id, factory_id):
    ticket, _ = ticket_for_user(db, user, ticket_id, factory_id)
    messages = db.scalars(select(FeedbackMessage).where(FeedbackMessage.ticket_id == ticket.id,
        FeedbackMessage.revision <= ticket.revision).order_by(FeedbackMessage.revision)).all()
    attachments = db.scalars(select(FeedbackAttachment).join(FeedbackMessage).where(FeedbackMessage.ticket_id == ticket.id,
        FeedbackMessage.revision <= ticket.revision)).all()
    by_message = {}
    for item in attachments:
        by_message.setdefault(item.message_id, []).append({
            "id": item.id, "file_name": item.file_name, "content_type": item.content_type, "size": item.size, "sha256": item.sha256,
            "url": f"/api/module-feedback/{ticket.id}/attachments/{item.id}?factory_id={factory_id}"})
    return _summary(db, user, ticket) | {"messages": [
        {key: getattr(message, key) for key in ("id", "actor_name", "actor_kind", "body", "action", "created_at", "revision",
                                               "requested_materials", "provided_materials", "release_note")}
        | {"attachments": by_message.get(message.id, [])} for message in messages]}


def list_tickets(db, user, factory_id, module, view, status, q, page, page_size):
    caps = capabilities(user, factory_id, module)
    if not (caps["can_manage"] or (view == "mine" and caps["can_submit"])):
        raise HTTPException(403, "未获此反馈列表权限")
    conditions = [FeedbackTicket.factory_id == factory_id, FeedbackTicket.module == module]
    if view == "mine":
        conditions.append(FeedbackTicket.author_id == user.id)
    unread_count = db.scalar(select(func.count()).select_from(FeedbackTicket).where(*conditions, _unread_clause(user)))
    if status:
        conditions.append(FeedbackTicket.status == status)
    if q:
        conditions.append(FeedbackTicket.title.contains(q, autoescape=True))
    total = db.scalar(select(func.count()).select_from(FeedbackTicket).where(*conditions))
    rows = db.execute(select(FeedbackTicket, _unread_clause(user)).where(*conditions)
        .order_by(FeedbackTicket.updated_at.desc(), FeedbackTicket.id).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_summary(db, user, row, unread=bool(unread)) for row, unread in rows],
            "total": total, "unread_count": unread_count, "page": page, "page_size": page_size}


def create_ticket(db: Session, user, payload, uploads):
    caps = require_submit(user, payload.factory_id, payload.module)
    fingerprint = _request_hash(payload, uploads)
    retry_conditions = (FeedbackTicket.factory_id == payload.factory_id, FeedbackTicket.author_id == user.id,
                        FeedbackTicket.client_request_id == payload.client_request_id)
    previous = db.scalar(select(FeedbackTicket).where(*retry_conditions))
    if previous:
        _check_retry(previous, fingerprint)
        return detail(db, user, previous.id, payload.factory_id)
    if payload.context.order_id and not caps["can_link_order"]:
        raise HTTPException(403, "未获订单查看权限，请移除订单关联后反馈；可在说明中主动提供参考号")
    if not payload.body and not uploads:
        raise HTTPException(422, "请输入问题说明或添加附件")
    context = payload.context.model_dump()
    if context["order_id"]:
        line = db.scalar(select(OrderLedgerLine).where(OrderLedgerLine.id == context["order_id"], OrderLedgerLine.factory_id == payload.factory_id))
        if line is None:
            raise HTTPException(404, "关联订单不存在或不属于当前厂区")
        context.update(order_reference=line.reference_no, product_no=line.product_no, customer_code=line.customer_code)
    now = _now()
    ticket = FeedbackTicket(id=_id(), factory_id=payload.factory_id, module=payload.module, author_id=user.id,
        author_name=user.display_name or user.username, title=payload.title, category=payload.category, emoji=payload.emoji,
        status="submitted", assigned_name="", context=context, requested_materials=[], provided_materials=[], release_note="",
        revision=1, client_request_id=payload.client_request_id, request_hash=fingerprint, created_at=now, updated_at=now)
    try:
        db.add(ticket)
        db.flush()
        _add_message(db, ticket, user, payload.body, "submit", "user", payload.client_request_id, fingerprint, uploads)
        _mark_read(db, user, ticket, 1)
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(select(FeedbackTicket).where(*retry_conditions))
        if not previous:
            raise
        _check_retry(previous, fingerprint)
        return detail(db, user, previous.id, payload.factory_id)
    return detail(db, user, ticket.id, payload.factory_id)


def reply(db, user, ticket_id, factory_id, payload, uploads):
    ticket, caps = ticket_for_user(db, user, ticket_id, factory_id)
    owner = ticket.author_id == user.id and caps["can_submit"]
    developer = caps["can_manage"]
    if payload.action in {"resolve", "reopen"}:
        allowed = owner
    elif payload.action in {"start", "request_info", "ready"}:
        allowed = developer
    else:
        allowed = owner or developer
    if not allowed:
        raise HTTPException(403, "无权执行此反馈操作")
    kind = "user" if owner and payload.action in {"reply", "resolve", "reopen"} else "developer"
    fingerprint = _request_hash(payload, uploads)
    retry_conditions = (FeedbackMessage.ticket_id == ticket.id, FeedbackMessage.actor_id == user.id,
                        FeedbackMessage.client_request_id == payload.client_request_id)
    previous = db.scalar(select(FeedbackMessage).where(*retry_conditions))
    if previous:
        _check_retry(previous, fingerprint)
        return detail(db, user, ticket.id, factory_id)
    if ticket.revision != payload.expected_revision:
        raise HTTPException(409, "反馈已有新回复，请刷新后操作")
    if ticket.status == "resolved" and payload.action != "reopen":
        raise HTTPException(409, "已解决反馈须由用户重新打开后继续回复")
    if payload.requested_materials and payload.action != "request_info":
        raise HTTPException(422, "仅开发人员请求补充时可设置材料清单")
    if payload.release_note and payload.action != "ready":
        raise HTTPException(422, "发布说明仅用于请用户验证操作")
    if payload.provided_materials:
        if kind != "user" or payload.action != "reply" or not set(payload.provided_materials).issubset(ticket.requested_materials):
            raise HTTPException(422, "只能提交当前请求的补充材料")
        if any(x in payload.provided_materials for x in ("screenshot", "original_file")) and not uploads:
            raise HTTPException(422, "所选补充材料需要附件")
        if "screenshot" in payload.provided_materials and not any(f.content_type.startswith("image/") for f in uploads):
            raise HTTPException(422, "截图材料需要图片附件")
        if any(x in payload.provided_materials for x in ("steps", "expected_result", "order_reference")) and not payload.body:
            raise HTTPException(422, "所选补充材料需要文字说明")
    if payload.action == "reply" and not payload.body and not uploads:
        raise HTTPException(422, "请输入回复或添加附件")
    new_status = ticket.status
    requested = list(ticket.requested_materials)
    provided = list(ticket.provided_materials)
    release_note = ticket.release_note
    if payload.action == "start":
        if ticket.status not in {"submitted", "needs_info", "in_progress"}:
            raise HTTPException(409, "当前状态不能开始处理")
        new_status = "in_progress"
    elif payload.action == "request_info":
        if ticket.status == "resolved":
            raise HTTPException(409, "已解决反馈须由用户重新打开")
        if not payload.requested_materials or not payload.body:
            raise HTTPException(422, "请填写补充说明并选择所需材料")
        new_status, requested, provided = "needs_info", payload.requested_materials, []
    elif payload.action == "ready":
        if ticket.status == "resolved":
            raise HTTPException(409, "已解决反馈须由用户重新打开")
        if not payload.release_note:
            raise HTTPException(422, "请填写已部署版本及修复说明")
        new_status, release_note = "awaiting_verification", payload.release_note
    elif payload.action == "resolve":
        if ticket.status != "awaiting_verification":
            raise HTTPException(409, "仅待用户验证的反馈可确认解决")
        new_status = "resolved"
    elif payload.action == "reopen":
        if ticket.status not in {"awaiting_verification", "resolved"} or not payload.body:
            raise HTTPException(422, "仅待验证或已解决反馈可重新打开，须说明原因")
        new_status = "submitted"
    if payload.provided_materials:
        provided = sorted(set(provided) | set(payload.provided_materials))
        if new_status == "needs_info" and requested and set(requested).issubset(provided):
            new_status = "in_progress"
    new_revision = ticket.revision + 1
    updated_at = _now()
    assigned_name = (user.display_name or user.username) if kind == "developer" else ticket.assigned_name
    try:
        changed = db.execute(update(FeedbackTicket).where(FeedbackTicket.id == ticket.id,
            FeedbackTicket.revision == payload.expected_revision).values(revision=new_revision, status=new_status,
            updated_at=updated_at, assigned_name=assigned_name, requested_materials=requested, provided_materials=provided,
            release_note=release_note).execution_options(synchronize_session=False)).rowcount
        if changed != 1:
            db.rollback()
            previous = db.scalar(select(FeedbackMessage).where(*retry_conditions))
            if previous:
                _check_retry(previous, fingerprint)
                return detail(db, user, ticket_id, factory_id)
            raise HTTPException(409, "反馈已有新回复，请刷新后操作")
        db.refresh(ticket)
        _add_message(db, ticket, user, payload.body, payload.action, kind, payload.client_request_id, fingerprint, uploads,
                     payload.requested_materials, payload.provided_materials, payload.release_note)
        _mark_read(db, user, ticket, payload.expected_revision)
        db.commit()
    except IntegrityError:
        db.rollback()
        previous = db.scalar(select(FeedbackMessage).where(*retry_conditions))
        if not previous:
            raise HTTPException(409, "反馈已有新回复，请刷新后操作")
        _check_retry(previous, fingerprint)
    return detail(db, user, ticket_id, factory_id)


def mark_read(db, user, ticket_id, factory_id, through_revision):
    ticket, _ = ticket_for_user(db, user, ticket_id, factory_id)
    if through_revision > ticket.revision:
        raise HTTPException(422, "不能标记尚未看到的回复")
    current = _read_revision(db, user, ticket)
    if through_revision > current:
        _mark_read(db, user, ticket, through_revision)
        db.commit()
    return {"through_revision": max(current, through_revision)}


def attachment(db, user, ticket_id, factory_id, attachment_id):
    ticket_for_user(db, user, ticket_id, factory_id)
    row = db.scalar(select(FeedbackAttachment).join(FeedbackMessage).where(
        FeedbackAttachment.id == attachment_id, FeedbackMessage.ticket_id == ticket_id))
    if row is None:
        raise HTTPException(404, "附件不存在")
    return row
