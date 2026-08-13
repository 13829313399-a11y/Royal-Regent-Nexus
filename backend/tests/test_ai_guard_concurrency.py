from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from time import sleep

from ai_guard_helpers import (
    pilot_user,
    shared_guard,
    shared_settings,
)
from app.services.ai.pilot_guard import AIPilotGuardError


def test_atomic_competition_allows_only_configured_concurrency(
    shared_guard_runtime,
):
    backend, _sessions, _engine = shared_guard_runtime
    settings = shared_settings(ai_pilot_requests_per_minute=60)
    start = Barrier(8)

    def compete(index: int) -> str:
        guard = shared_guard(
            backend,
            instance_id=f"instance:{index}",
            current=[datetime(2026, 8, 12, 8, 0, tzinfo=UTC)],
        )
        start.wait()
        try:
            lease = guard.acquire(
                user=pilot_user(),
                settings=settings,
                input_chars=1,
                has_attachments=False,
                factory_id="huaxing",
            )
        except AIPilotGuardError as exc:
            return exc.code
        sleep(0.1)
        lease.close()
        return "GRANTED"

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = tuple(executor.map(compete, range(8)))
    assert outcomes.count("GRANTED") == 1
    assert outcomes.count("AI_CONCURRENT_REQUEST_LIMIT") == 7
