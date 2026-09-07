"""Committed PostgreSQL notifications wake SSE; bounded snapshot recovery is durable."""

import asyncio
import json
import logging
import threading
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.db import SessionLocal
from app.models import three_d_printing as m
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)


class LiveHub:
    def __init__(self):
        self.subscribers = set()
        self.stop_event = threading.Event()
        self.thread = None

    def subscribe(self):
        queue = asyncio.Queue(maxsize=1)
        self.subscribers.add(queue)
        return queue

    def unsubscribe(self, queue):
        self.subscribers.discard(queue)

    def publish(self):
        for queue in tuple(self.subscribers):
            if not queue.full():
                queue.put_nowait(True)

    def start(self):
        if make_url(settings.database_url).get_backend_name() != "postgresql":
            return
        self.loop = asyncio.get_running_loop()
        self.stop_event.clear()
        self.thread = threading.Thread(
            target=self.listen, daemon=True, name="three-d-notify"
        )
        self.thread.start()

    def listen(self):
        import psycopg

        url = make_url(settings.database_url)
        while not self.stop_event.is_set():
            try:
                with psycopg.connect(
                    host=url.host,
                    port=url.port or 5432,
                    dbname=url.database,
                    user=url.username,
                    password=url.password,
                    **dict(url.query),
                    autocommit=True,
                    connect_timeout=3,
                ) as conn:
                    conn.execute("LISTEN three_d_printing_events")
                    self.loop.call_soon_threadsafe(self.publish)
                    while not self.stop_event.is_set():
                        for message in conn.notifies(timeout=1, stop_after=1):
                            body = json.loads(message.payload)
                            if body.get("factory_id") == "huakang-a":
                                self.loop.call_soon_threadsafe(self.publish)
            except (psycopg.Error, ValueError, OSError, RuntimeError, TypeError):
                logger.warning("three_d_notify_reconnecting")
                self.stop_event.wait(2)

    async def stop(self):
        self.stop_event.set()
        if self.thread:
            await asyncio.to_thread(self.thread.join, 5)
        self.subscribers.clear()


hub = LiveHub()


def snapshot(request, factory_id):
    from app.api.three_d_printing import _ensure_permission
    from app.services.three_d_network_health import (
        network_blocks_control,
        network_health_snapshot,
    )
    from app.services.three_d_printing import command_out, printer_out

    # No connection/transaction is held while waiting for a notification.
    with SessionLocal() as db:
        user = get_current_user(request, db)
        _ensure_permission(db, user, "three_d_printing:read", factory_id)
        printers = db.scalars(
            select(m.ThreeDPrintingPrinter)
            .where(
                m.ThreeDPrintingPrinter.factory_id == factory_id,
            )
            .order_by(m.ThreeDPrintingPrinter.machine_no)
        )
        stale = network_blocks_control(db)
        payload = {
            "printers": [printer_out(p, network_stale=stale) for p in printers],
            "network_health": network_health_snapshot(db),
        }
        commands = db.scalars(
            select(m.ThreeDPrintingPrinterCommand)
            .where(
                m.ThreeDPrintingPrinterCommand.factory_id == factory_id,
            )
            .order_by(m.ThreeDPrintingPrinterCommand.requested_at.desc())
            .limit(50)
        )
        payload["commands"] = [command_out(c) for c in commands]
        runs = db.execute(
            select(
                func.count(m.ThreeDPrintingProductionRecord.id),
                func.sum(m.ThreeDPrintingProductionRecord.revision),
            ).where(
                m.ThreeDPrintingProductionRecord.factory_id == factory_id,
            )
        ).one()
        payload["run_version"] = sha256(repr(runs).encode()).hexdigest()
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return sha256(encoded.encode()).hexdigest(), encoded


async def events(request, factory_id, initial, last_id=""):
    queue = hub.subscribe()
    version, encoded = initial
    try:
        # The cursor identifies a complete snapshot, not a lossy in-memory event offset.
        # A reconnect always replaces state from DB; no missed NOTIFY can lose truth.
        yield f"id: {version}\nevent: {'snapshot' if last_id == version else 'reset'}\ndata: {encoded}\n\n"
        while not await request.is_disconnected():
            try:
                await asyncio.wait_for(queue.get(), timeout=5)
            except TimeoutError:
                pass
            await asyncio.sleep(
                0.2
            )  # Coalesce bursts, bounded queue under slow clients.
            try:
                current, encoded = await asyncio.to_thread(
                    snapshot, request, factory_id
                )
            except HTTPException as error:
                yield f'event: access_revoked\ndata: {{"status":{error.status_code}}}\n\n'
                return
            if current != version:
                version = current
                yield f"id: {version}\nevent: snapshot\ndata: {encoded}\n\n"
            else:
                yield "event: ping\ndata: {}\n\n"
    finally:
        hub.unsubscribe(queue)
