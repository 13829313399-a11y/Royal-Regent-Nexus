from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.ai.task_lease import TaskLease, claim_next_task


class PostgreSQLTaskQueue:
    """Small queue boundary that keeps PostgreSQL replaceable by a later broker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def claim(
        self,
        db: Session,
        *,
        owner_instance: str,
        now: datetime | None = None,
    ) -> TaskLease | None:
        return claim_next_task(
            db,
            owner_instance=owner_instance,
            settings=self.settings,
            now=now,
        )
