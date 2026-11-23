"""Read a raw .eml file into headers, body text and attachments."""
import email
import hashlib
import html as html_lib
import re
from dataclasses import dataclass, field
from email import policy

_TAG = re.compile(r'<[^>]+>')
_BREAK = re.compile(r'<(?:br|/p|/div|/tr|/li)\s*/?>', re.IGNORECASE)
_CELL = re.compile(r'</(?:td|th)\s*>', re.IGNORECASE)
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


def html_to_text(raw_html: str) -> str:
    text = _BREAK.sub('\n', raw_html or '')
    text = _CELL.sub('  ', text)
    text = _TAG.sub(' ', text)
    text = html_lib.unescape(text)
    return '\n'.join(_SPACE.sub(' ', line).strip() for line in text.splitlines())


def _decode_text_part(part) -> str:
    try:
        content = part.get_content()
        if isinstance(content, str):
            return content
    except (LookupError, UnicodeDecodeError, ValueError, KeyError):
        pass
    raw = part.get_payload(decode=True)
    if not isinstance(raw, (bytes, bytearray)):
        return str(raw or '')
    charset = (part.get_content_charset() or '').strip()
    candidates = [c for c in (charset, 'utf-8', 'gb18030', 'big5', 'latin-1') if c]
    for enc in candidates:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode('utf-8', errors='replace')


def read_eml(raw: bytes) -> EmailMessage:
    message = email.message_from_bytes(raw, policy=policy.default)
    subject = _header(message.get('Subject'))
    sender = _header(message.get('From'))
    received_at = _header(message.get('Date'))
    bodies: list[str] = []
    attachments: list[EmailAttachment] = []
    for part in message.walk():
        if part.is_multipart():
            if part.get_content_type() == 'message/rfc822':
                nested_subj = _header(part.get('Subject'))
                if nested_subj and nested_subj not in subject:
                    bodies.append(nested_subj)
            continue
        filename = part.get_filename()
        content_type = part.get_content_type()
        payload = part.get_payload(decode=True) or b''
        if filename:
            attachments.append(EmailAttachment(_header(filename), content_type, payload))
            continue
        if content_type == 'text/plain':
            bodies.append(_decode_text_part(part))
        elif content_type == 'text/html':
            bodies.append(html_to_text(_decode_text_part(part)))
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
