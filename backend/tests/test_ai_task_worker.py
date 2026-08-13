from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from app.core.time import business_now
from app.models.ai_task import AITask, AITaskEvent, AITaskStep
from app.schemas.ai.task import AITaskState, AITaskStepState
from app.services.ai.providers import ProviderError, ProviderErrorCode, ProviderResponse
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.task_lease import (
    AITaskLeaseError,
    claim_next_task,
    renew_task_lease,
)
from app.services.ai.task_runner import run_claimed_task, run_with_heartbeat
from app.services.ai.task_service import request_task_cancellation, transition_task
from app.services.ai.tool_registry import build_default_tool_registry
from sqlalchemy import func, select
from tests.ai_task_worker_helpers import (
    compute_payload,
    create_worker_task,
    fake_task_payload,
    fake_task_skill_registry,
    tool_payload,
    worker_auth_loader,
    worker_database,
    worker_settings,
    worker_user,
)


class _FailingProvider(FakeProvider):
    def __init__(self, code: ProviderErrorCode, status_code: int) -> None:
        super().__init__()
        self.code = code
        self.status_code = status_code

    async def generate(self, request):
        self.requests.append(request)
        raise ProviderError(
            self.code,
            "bounded provider failure",
            status_code=self.status_code,
            retryable=True,
        )


class _BlockingProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def generate(self, request):
        self.requests.append(request)
        self.started.set()
        await self.release.wait()
        return ProviderResponse(text="must be discarded", response_id="cancel-race")


class _RecordingPilotLease:
    def __init__(self, calls: list[str]) -> None:
        self.calls = calls

    def mark_provider_started(self) -> None:
        self.calls.append("provider_started")

    def record_usage(self, total_tokens: int) -> None:
        self.calls.append(f"usage:{total_tokens}")

    def mark_completed(self) -> None:
        self.calls.append("completed")

    def close(self) -> None:
        self.calls.append("close")


class _RecordingPilotGuard:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def acquire(self, **kwargs):
        self.calls.append(f"acquire:{kwargs['factory_id']}")
        return _RecordingPilotLease(self.calls)


def test_two_workers_cannot_hold_the_same_task_lease(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'lease-race.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    task_id = create_worker_task(factory, settings=config)

    def claim(instance: str):
        with factory() as db:
            return claim_next_task(
                db,
                owner_instance=instance,
                settings=config,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(claim, ("worker-a", "worker-b")))
    claimed = [lease for lease in leases if lease is not None]
    assert len(claimed) == 1
    assert claimed[0].task_id == task_id
    with factory() as db:
        record = db.get(AITask, task_id)
        assert record is not None
        assert record.claim_count == 1
        assert db.scalar(
            select(func.count(AITaskEvent.id)).where(
                AITaskEvent.task_id == task_id,
                AITaskEvent.event_type == "LEASE_CLAIMED",
            )
        ) == 1


def test_lease_renews_and_expired_owner_cannot_heartbeat(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'heartbeat.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    create_worker_task(factory, settings=config)
    started = business_now()
    with factory() as db:
        lease = claim_next_task(
            db,
            owner_instance="worker-a",
            settings=config,
            now=started,
        )
    assert lease is not None
    with factory() as db:
        renewed = renew_task_lease(
            db,
            lease=lease,
            settings=config,
            now=started + timedelta(seconds=15),
        )
    assert renewed.expires_at == started + timedelta(seconds=105)
    with factory() as db:
        try:
            renew_task_lease(
                db,
                lease=renewed,
                settings=config,
                now=renewed.expires_at + timedelta(seconds=1),
            )
        except AITaskLeaseError as exc:
            assert exc.code == "AI_TASK_LEASE_LOST"
        else:
            raise AssertionError("expired lease unexpectedly renewed")


def test_fake_compute_task_runs_to_terminal_persistent_events(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'fake-task.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    task_id = create_worker_task(factory, settings=config)
    with factory() as db:
        lease = claim_next_task(
            db,
            owner_instance="worker-fake",
            settings=config,
        )
    assert lease is not None
    result = asyncio.run(
        run_claimed_task(
            session_factory=factory,
            lease=lease,
            settings=config,
            registry=build_default_tool_registry(controlled_apply_enabled=False),
            provider=FakeProvider(),
            auth_loader=worker_auth_loader,
        )
    )
    assert result == AITaskState.COMPLETED.value
    with factory() as db:
        task = db.get(AITask, task_id)
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task_id))
        assert task is not None and step is not None
        assert task.state == AITaskState.COMPLETED.value
        assert task.lease_token == ""
        assert step.state == AITaskStepState.COMPLETED.value
        assert step.attempt_count == 1
        assert step.result_hash.startswith("sha256:")
        assert "确定性的中文测试回复" not in step.result_metadata_json
        sequences = list(
            db.scalars(
                select(AITaskEvent.sequence)
                .where(AITaskEvent.task_id == task_id)
                .order_by(AITaskEvent.sequence)
            ).all()
        )
        assert sequences == list(range(1, len(sequences) + 1))


def test_worker_model_step_uses_the_injected_shared_guard_boundary(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'worker-shared-guard.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    create_worker_task(factory, settings=config)
    with factory() as db:
        lease = claim_next_task(
            db,
            owner_instance="worker-shared-guard",
            settings=config,
        )
    assert lease is not None
    pilot_guard = _RecordingPilotGuard()
    result = asyncio.run(
        run_claimed_task(
            session_factory=factory,
            lease=lease,
            settings=config,
            registry=build_default_tool_registry(controlled_apply_enabled=False),
            provider=FakeProvider(),
            auth_loader=worker_auth_loader,
            pilot_guard=pilot_guard,
        )
    )
    assert result == AITaskState.COMPLETED.value
    assert pilot_guard.calls == [
        "acquire:huaxing",
        "provider_started",
        "usage:0",
        "completed",
        "close",
    ]


def test_dedicated_fake_task_skill_runs_end_to_end(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'fake-skill-task.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    registry = build_default_tool_registry(controlled_apply_enabled=False)
    skill_registry = fake_task_skill_registry(registry)
    task_id = create_worker_task(
        factory,
        payload=fake_task_payload(),
        settings=config,
        skill_registry=skill_registry,
    )
    with factory() as db:
        lease = claim_next_task(
            db,
            owner_instance="worker-fake-skill",
            settings=config,
        )
    assert lease is not None
    provider = FakeProvider()
    result = asyncio.run(
        run_claimed_task(
            session_factory=factory,
            lease=lease,
            settings=config,
            registry=registry,
            provider=provider,
            auth_loader=worker_auth_loader,
            skill_registry=skill_registry,
        )
    )
    assert result == "COMPLETED"
    system_message = provider.requests[0].input[0]
    assert "test.fake_task@1.0.0" in system_message.content
    with factory() as db:
        task = db.get(AITask, task_id)
        assert task is not None
        assert task.primary_skill_id == "test.fake_task"
        assert task.state == "COMPLETED"


def test_worker_executes_registered_read_tool_without_business_table_access(
    tmp_path,
) -> None:
    database_url = f"sqlite:///{(tmp_path / 'tool-task.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    task_id = create_worker_task(
        factory,
        payload=tool_payload(),
        settings=config,
    )
    with factory() as db:
        lease = claim_next_task(
            db,
            owner_instance="worker-tool",
            settings=config,
        )
    assert lease is not None
    result = asyncio.run(
        run_claimed_task(
            session_factory=factory,
            lease=lease,
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
        assert step.result_hash.startswith("sha256:")
        assert '"kind":"TOOL_RESULT"' in step.result_metadata_json


def test_provider_429_and_5xx_have_finite_idempotent_recovery(tmp_path) -> None:
    for code, status_code in (
        (ProviderErrorCode.RATE_LIMITED, 429),
        (ProviderErrorCode.PROVIDER_UNAVAILABLE, 503),
    ):
        database_url = (
            f"sqlite:///{(tmp_path / f'provider-{status_code}.db').as_posix()}"
        )
        factory = worker_database(database_url)
        config = worker_settings(database_url)
        task_id = create_worker_task(
            factory,
            payload=None,
            settings=config,
        )
        provider = _FailingProvider(code, status_code)
        now = business_now()
        results: list[str] = []
        for attempt in range(3):
            with factory() as db:
                lease = claim_next_task(
                    db,
                    owner_instance=f"worker-{status_code}-{attempt}",
                    settings=config,
                    now=now,
                )
            assert lease is not None
            results.append(
                asyncio.run(
                    run_claimed_task(
                        session_factory=factory,
                        lease=lease,
                        settings=config,
                        registry=build_default_tool_registry(
                            controlled_apply_enabled=False
                        ),
                        provider=provider,
                        auth_loader=worker_auth_loader,
                    )
                )
            )
            with factory() as db:
                task = db.get(AITask, task_id)
                assert task is not None
                if task.next_attempt_at:
                    now = datetime.fromisoformat(task.next_attempt_at) + timedelta(
                        seconds=1
                    )
        assert results == ["RETRY_PENDING", "RETRY_PENDING", "FAILED"]
        with factory() as db:
            task = db.get(AITask, task_id)
            step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task_id))
            assert task is not None and step is not None
            assert task.failure_code == f"TASK_PROVIDER_{code.value.upper()}"
            assert step.attempt_count == 3
            assert step.max_attempts == 3


def test_cancellation_wins_race_and_discards_external_result(tmp_path) -> None:
    async def scenario() -> None:
        database_url = f"sqlite:///{(tmp_path / 'cancel-race.db').as_posix()}"
        factory = worker_database(database_url)
        config = worker_settings(database_url)
        task_id = create_worker_task(factory, settings=config)
        with factory() as db:
            lease = claim_next_task(
                db,
                owner_instance="cancel-race-worker",
                settings=config,
            )
        assert lease is not None
        provider = _BlockingProvider()
        running = asyncio.create_task(
            run_claimed_task(
                session_factory=factory,
                lease=lease,
                settings=config,
                registry=build_default_tool_registry(controlled_apply_enabled=False),
                provider=provider,
                auth_loader=worker_auth_loader,
            )
        )
        await asyncio.wait_for(provider.started.wait(), timeout=5)
        with factory() as db:
            task = db.get(AITask, task_id)
            assert task is not None
            request_task_cancellation(
                db,
                task=task,
                user=worker_user(),
                expected_revision=task.revision,
                reason_code="USER_CANCELLED",
                settings=config,
            )
            db.commit()
        provider.release.set()
        assert await asyncio.wait_for(running, timeout=5) == "CANCELLED"
        with factory() as db:
            task = db.get(AITask, task_id)
            step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task_id))
            assert task is not None and step is not None
            assert task.state == "CANCELLED"
            assert step.state == "CANCELLED"
            assert step.result_hash == ""

    asyncio.run(scenario())


def test_unclaimed_cancellation_is_claimed_and_reaches_terminal_state(tmp_path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'cancel-before-claim.db').as_posix()}"
    factory = worker_database(database_url)
    config = worker_settings(database_url)
    task_id = create_worker_task(factory, settings=config)
    with factory() as db:
        task = db.get(AITask, task_id)
        assert task is not None
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.UNDERSTOOD,
            actor_type="SYSTEM",
            reason_code="TASK_UNDERSTOOD",
            settings=config,
        )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.PLANNED,
            actor_type="SYSTEM",
            reason_code="TASK_PLANNED",
            settings=config,
        )
        request_task_cancellation(
            db,
            task=task,
            user=worker_user(),
            expected_revision=task.revision,
            reason_code="USER_CANCELLED",
            settings=config,
        )
        db.commit()
    with factory() as db:
        lease = claim_next_task(
            db,
            owner_instance="cancel-observer-worker",
            settings=config,
        )
    assert lease is not None
    result = asyncio.run(
        run_claimed_task(
            session_factory=factory,
            lease=lease,
            settings=config,
            registry=build_default_tool_registry(controlled_apply_enabled=False),
            provider=FakeProvider(),
            auth_loader=worker_auth_loader,
        )
    )
    assert result == "CANCELLED"
    with factory() as db:
        task = db.get(AITask, task_id)
        assert task is not None
        assert task.state == "CANCELLED"


def test_step_timeout_is_bounded_and_heartbeat_loss_stops_runner(
    tmp_path,
    monkeypatch,
) -> None:
    async def scenario() -> None:
        database_url = f"sqlite:///{(tmp_path / 'timeout-heartbeat.db').as_posix()}"
        factory = worker_database(database_url)
        config = worker_settings(database_url)
        config.ai_request_timeout_seconds = 0.01
        task_id = create_worker_task(factory, settings=config)
        with factory() as db:
            lease = claim_next_task(
                db,
                owner_instance="timeout-worker",
                settings=config,
            )
        assert lease is not None
        provider = _BlockingProvider()
        result = await run_claimed_task(
            session_factory=factory,
            lease=lease,
            settings=config,
            registry=build_default_tool_registry(controlled_apply_enabled=False),
            provider=provider,
            auth_loader=worker_auth_loader,
        )
        assert result == "RETRY_PENDING"
        with factory() as db:
            task = db.get(AITask, task_id)
            assert task is not None
            assert task.failure_code == "TASK_STEP_TIMEOUT"

        heartbeat_task_id = create_worker_task(
            factory,
            payload=compute_payload("worker-heartbeat-task-2"),
            settings=config,
        )
        with factory() as db:
            heartbeat_lease = claim_next_task(
                db,
                owner_instance="heartbeat-loss-worker",
                settings=config,
            )
        assert heartbeat_lease is not None
        assert heartbeat_lease.task_id == heartbeat_task_id
        config.ai_request_timeout_seconds = 5
        config.ai_task_worker_heartbeat_seconds = 0.01

        def fail_renew(*_args, **_kwargs):
            raise AITaskLeaseError("heartbeat unavailable")

        monkeypatch.setattr(
            "app.services.ai.task_lease.renew_task_lease",
            fail_renew,
        )
        with pytest.raises(AITaskLeaseError):
            await run_with_heartbeat(
                session_factory=factory,
                lease=heartbeat_lease,
                settings=config,
                registry=build_default_tool_registry(
                    controlled_apply_enabled=False
                ),
                provider=_BlockingProvider(),
                auth_loader=worker_auth_loader,
            )

    asyncio.run(scenario())
