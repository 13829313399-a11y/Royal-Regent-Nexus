from __future__ import annotations

import asyncio
from datetime import timedelta

from app.core.time import business_now
from app.models.ai_task import AITask, AITaskStep
from app.schemas.ai.task import AITaskState, AITaskStepState
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.task_lease import claim_next_task
from app.services.ai.task_runner import _recover_interrupted_step, run_claimed_task
from app.services.ai.task_service import transition_step, transition_task
from app.services.ai.tool_registry import build_default_tool_registry
from sqlalchemy import select
from tests.ai_task_worker_helpers import (
    create_worker_task,
    tool_payload,
    worker_auth_loader,
    worker_database,
    worker_settings,
)


def _simulate_crash(factory, *, task_id: str, config) -> None:
    with factory() as db:
        task = db.get(AITask, task_id)
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task_id))
        assert task is not None and step is not None
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.UNDERSTOOD,
            actor_type="SYSTEM",
            reason_code="WORKER_UNDERSTOOD_TASK",
            settings=config,
        )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.RUNNING,
            actor_type="SYSTEM",
            reason_code="WORKER_STARTED_TASK",
            settings=config,
        )
        transition_step(
            db,
            task=task,
            step=step,
            requested_state=AITaskStepState.RUNNING,
            actor_type="SYSTEM",
            reason_code="WORKER_STARTED_STEP",
        )
        step.attempt_count = 1
        db.commit()


def test_expired_safe_read_step_is_recovered_once(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'safe-recovery.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    task_id = create_worker_task(factory, payload=tool_payload(), settings=config)
    started = business_now()
    with factory() as db:
        first = claim_next_task(
            db,
            owner_instance="crashed-worker",
            settings=config,
            now=started,
        )
    assert first is not None
    _simulate_crash(factory, task_id=task_id, config=config)
    with factory() as db:
        recovered = claim_next_task(
            db,
            owner_instance="recovery-worker",
            settings=config,
            now=first.expires_at + timedelta(seconds=1),
        )
    assert recovered is not None
    result = asyncio.run(
        run_claimed_task(
            session_factory=factory,
            lease=recovered,
            settings=config,
            registry=build_default_tool_registry(controlled_apply_enabled=False),
            provider=FakeProvider(),
            auth_loader=worker_auth_loader,
        )
    )
    assert result == AITaskState.COMPLETED.value
    with factory() as db:
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task_id))
        assert step is not None
        assert step.attempt_count == 2
        assert step.state == AITaskStepState.COMPLETED.value


def test_expired_non_idempotent_preview_is_not_replayed(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'unsafe-recovery.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    task_id = create_worker_task(factory, payload=tool_payload("unsafe-preview"), settings=config)
    started = business_now()
    with factory() as db:
        first = claim_next_task(
            db,
            owner_instance="crashed-preview-worker",
            settings=config,
            now=started,
        )
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task_id))
        assert step is not None
        step.side_effect_class = "PREVIEW_STATE"
        step.idempotent = 0
        db.commit()
    assert first is not None
    _simulate_crash(factory, task_id=task_id, config=config)
    with factory() as db:
        recovered = claim_next_task(
            db,
            owner_instance="manual-review-worker",
            settings=config,
            now=first.expires_at + timedelta(seconds=1),
        )
    assert recovered is not None
    result = asyncio.run(
        run_claimed_task(
            session_factory=factory,
            lease=recovered,
            settings=config,
            registry=build_default_tool_registry(controlled_apply_enabled=False),
            provider=FakeProvider(),
            auth_loader=worker_auth_loader,
        )
    )
    assert result == AITaskState.FAILED.value
    with factory() as db:
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task_id))
        assert step is not None
        assert step.attempt_count == 1
        assert step.failure_code == "TASK_WORKER_CRASH_MANUAL_REVIEW"


def test_expired_keyed_artifact_preview_is_recoverable(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'artifact-recovery.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url).model_copy(
        update={
            "ai_artifacts_enabled": True,
            "ai_artifact_workflows_enabled": True,
        }
    )
    task_id = create_worker_task(factory, payload=tool_payload(), settings=config)
    _simulate_crash(factory, task_id=task_id, config=config)
    registry = build_default_tool_registry(artifact_workflows_enabled=True)

    with factory() as db:
        task = db.get(AITask, task_id)
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task_id))
        assert task is not None and step is not None
        spec = registry.resolve("artifacts.inspect_workbook")
        assert spec is not None
        step.tool_name = spec.name
        step.tool_version = spec.version
        step.side_effect_class = spec.side_effect_class.value
        step.idempotent = 1
        db.commit()

        assert _recover_interrupted_step(
            db,
            task=task,
            registry=registry,
            settings=config,
        ) is True
        db.commit()
        assert task.state == AITaskState.RETRY_PENDING.value
        assert step.state == AITaskStepState.RETRY_PENDING.value
        assert step.failure_code == "TASK_WORKER_CRASH_RECOVERABLE"
