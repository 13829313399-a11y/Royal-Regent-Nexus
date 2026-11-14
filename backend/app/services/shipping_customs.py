"""Capture 出货资料 / 通关一体化资料 attachments from shipping emails."""
import email
from datetime import datetime
from email import policy
from uuid import uuid4

from sqlalchemy import select

from app.models.shipping_mail import ShippingCustomsDoc
from app.services.auth import AuthContext
from app.services.shipping_mail_service import authorize

KEYWORDS = ('通关一体化', '出货资料', '装箱单')
ALLOWED = ('.xls', '.xlsx', '.pdf', '.xlsm')


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def capture_from_eml(db, factory_id: str, mail_item_id: str, raw: bytes, fields: dict | None = None) -> int:
    try:
        message = email.message_from_bytes(raw, policy=policy.default)
    except Exception:  # noqa: BLE001
        return 0
    subject = str(message.get('Subject') or '')
    saved = 0
    fields = fields or {}
    port = str(fields.get('from_port') or fields.get('terminal') or '')[:120]
    container_type = str(fields.get('container_type') or '')[:60]
    si_cutoff = str(fields.get('cutoff_date') or '')[:40]
    for part in message.walk():
        filename = part.get_filename()
        if not filename:
            continue
        lower = filename.lower()
        if not lower.endswith(ALLOWED):
            continue
        if not (any(keyword in subject for keyword in KEYWORDS) or '装箱单' in filename):
            continue
        payload = part.get_payload(decode=True) or b''
        if not payload:
            continue
        existing = db.scalar(select(ShippingCustomsDoc.id).where(
            ShippingCustomsDoc.factory_id == factory_id,
            ShippingCustomsDoc.mail_item_id == mail_item_id,
            ShippingCustomsDoc.filename == filename[:500],
        ))
        if existing:
            continue
        db.add(ShippingCustomsDoc(
            id=f'customs-{uuid4().hex}', factory_id=factory_id, mail_item_id=mail_item_id,
            subject=subject[:500], port=port, container_type=container_type, si_cutoff=si_cutoff,
            special_note='', filename=filename[:500], content=payload,
            created_at=_now(), read_at='',
        ))
        saved += 1
    return saved


def _doc(row: ShippingCustomsDoc) -> dict:
    return {
        'id': row.id, 'factory_id': row.factory_id, 'subject': row.subject,
        'port': row.port, 'container_type': row.container_type, 'si_cutoff': row.si_cutoff,
        'special_note': row.special_note,
        'filename': row.filename, 'size': len(row.content or b''),
        'created_at': row.created_at, 'read': bool(row.read_at),
    }


def list_docs(db, user: AuthContext, factory_id: str, limit: int = 200) -> dict:
    authorize(user, factory_id, 'read')
    rows = db.scalars(
        select(ShippingCustomsDoc)
        .where(ShippingCustomsDoc.factory_id == factory_id)
        .order_by(ShippingCustomsDoc.created_at.desc())
        .limit(limit)
    ).all()
    unread = sum(1 for row in rows if not row.read_at)
    return {'docs': [_doc(row) for row in rows], 'unread': unread}


def mark_read(db, user: AuthContext, factory_id: str) -> dict:
    authorize(user, factory_id, 'read')
    rows = db.scalars(select(ShippingCustomsDoc).where(
        ShippingCustomsDoc.factory_id == factory_id, ShippingCustomsDoc.read_at == '',
    )).all()
    now = _now()
    for row in rows:
        row.read_at = now
    db.commit()
    return {'marked': len(rows)}


def get_content(db, user: AuthContext, factory_id: str, doc_id: str) -> tuple[str, bytes]:
    authorize(user, factory_id, 'read')
    row = db.scalar(select(ShippingCustomsDoc).where(
        ShippingCustomsDoc.id == doc_id, ShippingCustomsDoc.factory_id == factory_id,
    ))
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(404, '资料不存在')
    return row.filename, row.content
