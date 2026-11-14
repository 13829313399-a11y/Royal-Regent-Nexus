"""Read a raw .eml file into headers, body text and attachments."""
import email
import hashlib
import re
from dataclasses import dataclass, field
from email import policy

_TAG = re.compile(r'<[^>]+>')
_BREAK = re.compile(r'<(?:br|/p|/div|/tr)\s*/?>', re.IGNORECASE)
_SPACE = re.compile(r'[ \t\u00a0]{2,}')


@dataclass
class EmailAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class EmailMessage:
    subject: str
    sender: str
    received_at: str
    body_text: str
    attachments: list[EmailAttachment] = field(default_factory=list)
    fingerprint: str = ''


def html_to_text(html: str) -> str:
    text = _BREAK.sub('\n', html or '')
    text = _TAG.sub(' ', text)
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    return '\n'.join(_SPACE.sub(' ', line).strip() for line in text.splitlines())


def read_eml(raw: bytes) -> EmailMessage:
    message = email.message_from_bytes(raw, policy=policy.default)
    subject = _header(message.get('Subject'))
    sender = _header(message.get('From'))
    received_at = _header(message.get('Date'))
    bodies: list[str] = []
    attachments: list[EmailAttachment] = []
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True) or b''
        if filename:
            attachments.append(EmailAttachment(_header(filename), content_type, payload))
            continue
        if content_type == 'text/plain':
            body = part.get_content()
            bodies.append(body if isinstance(body, str) else str(body))
        elif content_type == 'text/html':
            body = part.get_content()
            bodies.append(html_to_text(body if isinstance(body, str) else str(body)))
    return EmailMessage(
        subject=subject,
        sender=sender,
        received_at=received_at,
        body_text='\n'.join(item for item in bodies if item).strip(),
        attachments=attachments,
        fingerprint=hashlib.sha256(raw).hexdigest(),
    )


def _header(value) -> str:
    if value is None:
        return ''
    return str(value).replace('\r', ' ').replace('\n', ' ').strip()
