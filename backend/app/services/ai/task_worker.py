from __future__ import annotations

import asyncio
import logging
import os
import socket
from contextlib import suppress
from datetime import timedelta
from uuid import uuid4

from app.core.config import settings
from app.core.time import business_now
from app.db import SessionLocal, engine
from app.services.ai.runtime_gate import is_ai_runtime_disabled
from app.services.ai.task_lease import clear_owned_lease, release_task_lease
from app.services.ai.task_queue import PostgreSQLTaskQueue
from app.services.ai.task_runner import (
    AITaskRunnerError,
    fail_claimed_task,
    run_with_heartbeat,
)
from app.services.ai.tool_registry import build_default_tool_registry

logger = logging.getLogger("app.ai.task_worker")


def _validate_worker_startup() -> None:
    if not settings.ai_task_worker_enabled:
        raise RuntimeError("AI Task Worker is disabled")
    if engine.dialect.name != "postgresql":
        raise RuntimeError("AI Task Worker requires PostgreSQL")
    if not (
        settings.ai_enabled
        and settings.ai_tasks_enabled
        and settings.ai_nif_runtime_enabled
        and settings.ai_skill_router_enabled
        and settings.ai_evidence_v1_enabled
    ):
        raise RuntimeError("AI Task Worker dependency flags are not enabled")
    if (
        settings.ai_task_worker_heartbeat_seconds * 2
        >= settings.ai_task_worker_lease_seconds
    ):
        raise RuntimeError(
            "AI Task Worker heartbeat does not leave a safe lease margin"
        )
    if settings.ai_artifact_workflows_enabled and not settings.ai_artifacts_enabled:
        raise RuntimeError("Artifact workflows require the Artifact foundation")
    if settings.ai_document_studio_enabled and not (
        settings.ai_artifacts_enabled
        and settings.ai_artifact_workflows_enabled
        and settings.ai_tasks_enabled
    ):
        raise RuntimeError("Document Studio requires Artifact and Task workflows")
    if (
        settings.ai_artifact_workflows_enabled
        and settings.ai_artifact_scanner_backend != "clamav"
    ):
        raise RuntimeError("Artifact workflow Worker requires ClamAV")
    if settings.ai_vision_tool_comparison_enabled and not (
        settings.ai_artifact_workflows_enabled
        and settings.ai_semantic_gateway_enabled
        and settings.ai_provider_capability_router_enabled
        and settings.ai_cloud_vision_enabled
    ):
        raise RuntimeError(
            "Vision comparison Worker dependencies are not enabled"
        )


async def _worker_slot(slot: int, stop: asyncio.Event) -> None:
    queue = PostgreSQLTaskQueue(settings)
    registry = build_default_tool_registry(
        controlled_apply_enabled=False,
        semantic_gateway_enabled=settings.ai_semantic_gateway_enabled,
        knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
        artifact_workflows_enabled=settings.ai_artifact_workflows_enabled,
        document_studio_enabled=settings.ai_document_studio_enabled,
        vision_tool_comparison_enabled=settings.ai_vision_tool_comparison_enabled,
    )
    instance = f"{socket.gethostname()}:{os.getpid()}:{slot}:{uuid4().hex[:12]}"
    while not stop.is_set():
        if is_ai_runtime_disabled(settings):
            await asyncio.sleep(settings.ai_task_worker_poll_seconds)
            continue
        lease = None
        try:
            with SessionLocal() as db:
                lease = queue.claim(db, owner_instance=instance)
            if lease is None:
                await asyncio.sleep(settings.ai_task_worker_poll_seconds)
                continue
            result = await run_with_heartbeat(
                session_factory=SessionLocal,
                lease=lease,
                settings=settings,
                registry=registry,
            )
            logger.info(
                "ai_task_worker task_id=%s slot=%s result=%s",
                lease.task_id,
                slot,
                result,
            )
        except asyncio.CancelledError:
            raise
        except AITaskRunnerError as exc:
            logger.exception(
                "ai_task_worker task_id=%s slot=%s status=failed",
                lease.task_id if lease is not None else "",
                slot,
            )
            if lease is not None:
                if exc.code == "TASK_RUNTIME_DISABLED" or exc.retryable:
                    with suppress(Exception), SessionLocal() as db:
                        release_task_lease(
                            db,
                            lease=lease,
                            reason_code=(
                                "WORKER_RUNTIME_DISABLED"
                                if exc.code == "TASK_RUNTIME_DISABLED"
                                else "WORKER_RETRYABLE_PREFLIGHT"
                            ),
                            next_attempt_at=business_now() + timedelta(seconds=30),
                        )
                else:
                    with suppress(Exception):
                        fail_claimed_task(
                            session_factory=SessionLocal,
                            lease=lease,
                            settings=settings,
                            failure_code=exc.code,
                        )
            await asyncio.sleep(settings.ai_task_worker_poll_seconds)
        except Exception:
            logger.exception(
                "ai_task_worker task_id=%s slot=%s status=crashed",
                lease.task_id if lease is not None else "",
                slot,
            )
            if lease is not None:
                with suppress(Exception), SessionLocal() as db:
                    clear_owned_lease(
                        db,
                        task_id=lease.task_id,
                        owner_instance=lease.owner_instance,
                        token=lease.token,
                    )
            await asyncio.sleep(settings.ai_task_worker_poll_seconds)


async def worker_main() -> None:
    _validate_worker_startup()
    stop = asyncio.Event()
    workers = [
        asyncio.create_task(_worker_slot(slot, stop), name=f"ai-task-worker:{slot}")
        for slot in range(settings.ai_task_worker_concurrency)
    ]
    try:
        await asyncio.gather(*workers)
    finally:
        stop.set()
        for worker in workers:
            worker.cancel()
        for worker in workers:
            with suppress(asyncio.CancelledError):
                await worker


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(worker_main())
