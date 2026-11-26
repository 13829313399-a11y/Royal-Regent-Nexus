"""IMAP fetch helpers and credential encryption for the shipping mail collector."""
import base64
import hashlib
import imaplib
from datetime import date, timedelta
from email import message_from_bytes
from email.header import decode_header, make_header

from app.core.config import settings


class ImapError(RuntimeError):
    pass


def _fernet():
    from cryptography.fernet import Fernet

    secret = settings.shipping_mail_imap_secret.get_secret_value()
    if not secret:
        raise ImapError('未配置 SHIPPING_MAIL_IMAP_SECRET，无法保存或读取邮箱密码')
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode('utf-8')).digest())
    return Fernet(key)


def encrypt_password(password: str) -> str:
    if not password:
        return ''
    return _fernet().encrypt(password.encode('utf-8')).decode('ascii')


def decrypt_password(value: str) -> str:
    if not value:
        return ''
    try:
        return _fernet().decrypt(value.encode('ascii')).decode('utf-8')
    except Exception as error:  # noqa: BLE001
        raise ImapError('邮箱密码解密失败，请重新保存邮箱配置') from error


def _connect(host: str, port: int, use_ssl: bool):
    if not host.strip():
        raise ImapError('请填写邮件服务器')
    try:
        if use_ssl:
            return imaplib.IMAP4_SSL(host.strip(), port, timeout=30)
        conn = imaplib.IMAP4(host.strip(), port, timeout=30)
        conn.starttls()
        return conn
    except OSError as error:
        raise ImapError(f'连接邮件服务器失败：{error}') from error


def _identify(conn) -> None:
    """Send the IMAP ID command required by NetEase (163/126) mailboxes."""
    imaplib.Commands['ID'] = ('AUTH',)
    try:
        conn._simple_command(
            'ID',
            '("name" "dsh-shipping" "version" "1.0" "vendor" "royal-regent-nexus")',
        )
        conn._untagged_response('OK', [None], 'ID')
    except Exception:  # noqa: BLE001 - servers without ID support ignore it
        pass


def _message_label(uid: str, raw: bytes) -> str:
    try:
        message = message_from_bytes(raw)
        subject = str(make_header(decode_header(str(message.get('Subject') or '')))).strip()
    except Exception:  # noqa: BLE001
        subject = ''
    if not subject:
        return f'mail-{uid}.eml'
    return f"{subject[:120]}.eml"


def _login(conn, host: str, username: str, password: str) -> None:
    """Log in; NetEase requires an IMAP ID handshake and an authorization code."""
    username = username.strip()
    password = password.replace(' ', '').strip()
    is_netease = any(token in host.lower() for token in ('163.com', '126.com', 'yeah.net', 'qiye.163.com'))
    if is_netease:
        _identify(conn)
    try:
        conn.login(username, password)
    except imaplib.IMAP4.error as error:
        if not is_netease:
            raise
        # Some NetEase tenants require ID before accepting LOGIN.
        _identify(conn)
        try:
            conn.login(username, password)
        except imaplib.IMAP4.error:
            raise ImapError(
                '邮箱登录失败：请确认已开启 IMAP/SMTP，并使用网易邮箱生成的授权码，'
                '不要使用网页登录密码。'
            ) from error
    _identify(conn)


def test_connection(host: str, port: int, username: str, password: str, use_ssl: bool, folder: str) -> None:
    conn = _connect(host, port, use_ssl)
    try:
        _login(conn, host, username, password)
        status, _ = conn.select(folder or 'INBOX', readonly=True)
        if status != 'OK':
            raise ImapError(f'无法打开邮箱文件夹 {folder or "INBOX"}')
    except imaplib.IMAP4.error as error:
        raise ImapError(f'邮箱登录失败：{error}') from error
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


def fetch_recent(
    host: str,
    port: int,
    username: str,
    password: str,
    use_ssl: bool,
    folder: str,
    *,
    since_days: int = 8,
    limit: int = 50,
    last_uid: str = '',
) -> list[tuple[str, str, bytes]]:
    """Return [(uid, filename, raw .eml)] for messages since ``since_days`` days."""
    conn = _connect(host, port, use_ssl)
    messages: list[tuple[str, str, bytes]] = []
    try:
        _login(conn, host, username, password)
        status, _ = conn.select(folder or 'INBOX', readonly=True)
        if status != 'OK':
            raise ImapError(f'无法打开邮箱文件夹 {folder or "INBOX"}')
        since = (date.today() - timedelta(days=max(1, since_days))).strftime('%d-%b-%Y')
        status, data = conn.uid('SEARCH', None, f'(SINCE {since})')
        if status != 'OK':
            raise ImapError('读取邮件列表失败')
        uids = [uid.decode('ascii') for uid in (data[0] or b'').split()]
        floor = int(last_uid) if last_uid.isdigit() else 0
        for uid in uids:
            if uid.isdigit() and int(uid) <= floor:
                continue
            status, parts = conn.uid('FETCH', uid, '(RFC822)')
            if status != 'OK' or not parts:
                continue
            raw = parts[0][1] if isinstance(parts[0], tuple) else b''
            if raw:
                messages.append((uid, _message_label(uid, raw), raw))
        return messages[-limit:]
    except imaplib.IMAP4.error as error:
        raise ImapError(f'收取邮件失败：{error}') from error
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
