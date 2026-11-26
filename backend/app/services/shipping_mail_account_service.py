"""Per-factory IMAP mailbox configuration, connection test and weekly sync."""
import json
from datetime import date, datetime
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import settings
from app.models.shipping_mail import ShippingMailAccount, ShippingMailItem, ShippingMailSyncRun
from app.services.auth import AuthContext
from app.services.shipping_mail.imap import (
    ImapError,
    decrypt_password,
    encrypt_password,
    fetch_recent,
    test_connection,
)
from app.services.shipping_mail_service import (
    SHIPPING_FACTORIES,
    _loads,
    _new_task,
    authorize,
    create_batch_internal,
)
from app.services.shipping_schedule import resolve_planned_ship_date


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _new_id(prefix: str) -> str:
    return f'{prefix}-{uuid4().hex}'


def configured_factories() -> list[str]:
    return [
        factory_id.strip()
        for factory_id in settings.shipping_mail_imap_factories.split(',')
        if factory_id.strip() in SHIPPING_FACTORIES
    ]


def get_account(db, factory_id: str) -> ShippingMailAccount | None:
    return db.scalar(select(ShippingMailAccount).where(ShippingMailAccount.factory_id == factory_id))


def account_payload(account: ShippingMailAccount | None) -> dict:
    if account is None:
        return {'configured': False, 'factory_id': '', 'host': '', 'port': 993, 'username': '',
                'use_ssl': True, 'folder': 'INBOX', 'enabled': False, 'has_password': False,
                'last_sync_at': '', 'last_status': 'idle', 'last_error': ''}
    return {
        'configured': True,
        'factory_id': account.factory_id,
        'host': account.host,
        'port': account.port,
        'username': account.username,
        'use_ssl': account.use_ssl,
        'folder': account.folder,
        'enabled': account.enabled,
        'has_password': bool(account.password_enc),
        'last_sync_at': account.last_sync_at,
        'last_status': account.last_status,
        'last_error': account.last_error,
    }


def save_account(db, user: AuthContext, payload: dict) -> dict:
    factory_id = str(payload.get('factory_id') or '')
    authorize(user, factory_id, 'import')
    host = str(payload.get('host') or '').strip()
    username = str(payload.get('username') or '').strip()
    if not host or not username:
        raise HTTPException(422, '请填写邮件服务器和邮箱地址')
    password = str(payload.get('password') or '')
    account = get_account(db, factory_id)
    if account is not None and username != account.username and not password:
        raise HTTPException(422, '更换邮箱地址后必须重新填写新邮箱的授权码')
    if account is not None and not password and not account.password_enc:
        raise HTTPException(422, '请填写网易邮箱授权码')
    if account is None:
        if not password:
            raise HTTPException(422, '首次配置需要填写邮箱密码')
        account = ShippingMailAccount(
            id=_new_id('mailacct'), factory_id=factory_id,
            created_at=_now(), updated_at=_now(), last_uid='', last_sync_at='',
            last_status='idle', last_error='',
        )
        db.add(account)
    if password:
        account.password_enc = encrypt_password(password)
    account.host = host
    account.port = int(payload.get('port') or 993)
    account.username = username
    account.use_ssl = bool(payload.get('use_ssl', True))
    account.folder = str(payload.get('folder') or 'INBOX').strip() or 'INBOX'
    account.enabled = bool(payload.get('enabled', True))
    account.updated_at = _now()
    db.commit()
    return account_payload(account)


def test_account(db, user: AuthContext, factory_id: str, password: str = '') -> dict:
    authorize(user, factory_id, 'import')
    account = get_account(db, factory_id)
    if account is None:
        raise HTTPException(404, '该厂区尚未配置邮箱')
    try:
        secret = password or decrypt_password(account.password_enc)
        test_connection(account.host, account.port, account.username, secret, account.use_ssl, account.folder)
        return {'ok': True, 'message': '邮箱连接成功'}
    except ImapError as error:
        account.password_enc = ''
        account.last_status = 'error'
        account.last_error = str(error)
        account.updated_at = _now()
        db.commit()
        raise HTTPException(400, str(error)) from error


def sync_account(db, factory_id: str, *, trigger: str = 'manual', user: AuthContext | None = None) -> dict:
    account = get_account(db, factory_id)
    if account is None:
        raise HTTPException(404, '该厂区尚未配置邮箱')
    if not account.enabled:
        raise HTTPException(409, '该厂区邮箱已停用')
    started = _now()
    run = ShippingMailSyncRun(
        id=_new_id('mailrun'), factory_id=factory_id, trigger=trigger, status='running',
        fetched=0, imported=0, confirmed=0, failed=0, message='', started_at=started, finished_at='',
    )
    db.add(run)
    db.commit()
    generated_task_ids: list[str] = []
    try:
        password = decrypt_password(account.password_enc)
        messages = fetch_recent(
            account.host, account.port, account.username, password, account.use_ssl, account.folder,
            last_uid=account.last_uid,
        )
        run.fetched = len(messages)
        if messages:
            result = create_batch_internal(
                db, factory_id, [(name, raw) for _, name, raw in messages],
                created_by='system:imap', source='imap',
            )
            item_ids = [item['id'] for item in result.get('items') or []]
            run.imported = len(item_ids)
            run.confirmed = 0
            generated_task_ids = []
            run.message = f'拉取 {len(messages)} 封，新增 {run.imported} 封'
            if result.get('duplicates'):
                run.message += f'，跳过重复 {result["duplicates"]} 封'
            for item_id in item_ids:
                item = db.get(ShippingMailItem, item_id)
                if item is None or item.status != 'pending':
                    continue
                fields = json.loads(item.fields_json or '{}')
                if not str(fields.get('so_number') or '').strip():
                    continue
                planned = resolve_planned_ship_date(
                    ship_date=fields.get('ship_date', ''),
                    cutoff_date=fields.get('cutoff_date', ''),
                    si_deadline=fields.get('si_deadline', ''),
                    received_at=item.received_at,
                )
                if planned is None:
                    continue
                task = _new_task(
                    factory_id=factory_id, fields=fields, items=_loads(item.items_json),
                    source='mail', mail_item_id=item.id, warnings=_loads(item.warnings_json), planned=planned,
                )
                db.add(task)
                db.flush()
                item.status = 'confirmed'
                item.task_ids_json = json.dumps([task.id])
                item.updated_at = _now()
                generated_task_ids.append(task.id)
                run.confirmed += 1
            if run.confirmed:
                run.message += f'，自动生成 {run.confirmed} 条 SO 排期'
            max_uid = max((int(uid) for uid, _, _ in messages if uid.isdigit()), default=0)
            if max_uid:
                account.last_uid = str(max_uid)

        else:
            run.message = '没有新邮件'
        account.last_sync_at = _now()
        account.last_status = 'ok'
        account.last_error = ''
        run.status = 'ok'
    except (ImapError, HTTPException) as error:
        db.rollback()
        account.last_status = 'error'
        account.last_error = str(error)
        run.status = 'error'
        run.message = str(error)
    except Exception as error:  # noqa: BLE001 - 定时任务不能因单次同步中断
        db.rollback()
        account.last_status = 'error'
        account.last_error = f'{type(error).__name__}: {error}'
        run.status = 'error'
        run.message = account.last_error
    finally:
        run.finished_at = _now()
        account.updated_at = _now()
        db.add(run)
        db.add(account)
        db.commit()
        if generated_task_ids:
            try:
                from sqlalchemy import select as sa_select
                from app.models.auth import AuthUser
                from app.services.auth import build_auth_context
                from app.services.shipping_autogen import generate_for_task
                admin = db.scalar(sa_select(AuthUser).where(AuthUser.username == 'admin'))
                if admin is not None:
                    context = build_auth_context(db, admin)
                    for task_id in generated_task_ids:
                        generate_for_task(db, context, factory_id, task_id)
            except Exception:  # noqa: BLE001
                pass
    return run_payload(run)


def run_payload(run: ShippingMailSyncRun) -> dict:
    return {
        'id': run.id, 'factory_id': run.factory_id, 'trigger': run.trigger, 'status': run.status,
        'fetched': run.fetched, 'imported': run.imported, 'confirmed': run.confirmed,
        'failed': run.failed, 'message': run.message,
        'started_at': run.started_at, 'finished_at': run.finished_at,
    }


def list_runs(db, user: AuthContext, factory_id: str, limit: int = 20) -> list[dict]:
    authorize(user, factory_id, 'read')
    rows = db.scalars(
        select(ShippingMailSyncRun)
        .where(ShippingMailSyncRun.factory_id == factory_id)
        .order_by(ShippingMailSyncRun.started_at.desc())
        .limit(limit)
    ).all()
    return [run_payload(row) for row in rows]


def configured_weekdays() -> list[int]:
    days: list[int] = []
    for token in settings.shipping_mail_imap_weekdays.split(','):
        token = token.strip()
        if token.isdigit() and 0 <= int(token) <= 6 and int(token) not in days:
            days.append(int(token))
    return days or [3, 4, 5]


def auto_sync_window(now: datetime) -> bool:
    """Hourly collection window: from the start hour through 23:00; no runs after midnight."""
    return (
        now.weekday() in configured_weekdays()
        and settings.shipping_mail_imap_hour <= now.hour <= settings.shipping_mail_imap_end_hour
    )


def due_for_sync(account: ShippingMailAccount, now: datetime) -> bool:
    if not account.enabled:
        return False
    if not auto_sync_window(now):
        return False
    if not account.last_sync_at:
        return True
    try:
        last = datetime.fromisoformat(account.last_sync_at)
    except ValueError:
        return True
    if last.date() != date.today():
        return True
    return last.hour < now.hour
