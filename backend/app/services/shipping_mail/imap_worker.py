"""Weekly IMAP collector for the four shipping factories."""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.core.config import settings
from app.db import SessionLocal
from app.models.shipping_mail import ShippingMailAccount
from app.services.shipping_mail_account_service import (
    auto_sync_window,
    configured_factories,
    due_for_sync,
    sync_account,
)

logger = logging.getLogger('shipping_mail_imap')


def run_due_syncs(now: datetime | None = None) -> list[str]:
    if not settings.shipping_mail_imap_enabled:
        return []
    current = now or datetime.now()
    if not auto_sync_window(current):
        return []
    synced: list[str] = []
    with SessionLocal() as db:
        for factory_id in configured_factories():
            account = db.scalar(select(ShippingMailAccount).where(ShippingMailAccount.factory_id == factory_id))
            if account is None or not due_for_sync(account, current):
                continue
            try:
                sync_account(db, factory_id, trigger='weekly')
                synced.append(factory_id)
            except Exception:  # noqa: BLE001 - one factory must not stop the others
                logger.warning('shipping_imap_sync_failed factory=%s', factory_id, exc_info=True)
                db.rollback()
    return synced


async def worker() -> None:
    interval = max(30, settings.shipping_mail_imap_poll_seconds)
    while True:
        try:
            await asyncio.to_thread(run_due_syncs)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning('shipping_imap_worker_failed', exc_info=True)
        await asyncio.sleep(interval)
