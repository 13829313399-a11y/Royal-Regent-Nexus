"""Bounded maintenance for private staging files and replay events only."""
import asyncio
import logging
from datetime import timedelta
from sqlalchemy import select, func, delete
from app.db import SessionLocal
from app.models.collaboration import UserEvent, UserStream
from app.services.transaction_lock import lock_transaction
from app.services.identity_resolver import stamp, utc_now
from .assets import cleanup


def maintain():
    with SessionLocal() as db:
        cleanup(db)
        cutoff = stamp(utc_now() - timedelta(days=30))
        owners = list(db.execute(select(UserEvent.user_id, UserEvent.epoch).where(UserEvent.created_at < cutoff).distinct().limit(100)))
        db.rollback()
        for uid, epoch in owners:
            lock_transaction(db, "collab-stream", f"{uid}:{epoch}")
            stream = db.get(UserStream, (uid, epoch))
            first_recent = db.scalar(select(func.min(UserEvent.event_seq)).where(UserEvent.user_id == uid, UserEvent.epoch == epoch, UserEvent.created_at >= cutoff))
            if stream:
                floor = (first_recent - 1) if first_recent is not None else stream.last_event_seq
                db.execute(delete(UserEvent).where(UserEvent.user_id == uid, UserEvent.epoch == epoch, UserEvent.event_seq <= floor))
                stream.minimum_valid_cursor = max(stream.minimum_valid_cursor, floor)
            db.commit()


async def worker():
    while True:
        # Delay the first run so application startup does not compete with maintenance.
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(maintain)
        except Exception:
            logging.getLogger(__name__).exception("collaboration maintenance failed")
