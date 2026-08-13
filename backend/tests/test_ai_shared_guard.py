from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from ai_guard_helpers import (
    pilot_user,
    shared_guard,
    shared_settings,
)
from app.core.config import Settings
from app.models.ai_guard import AIGuardLease
from app.schemas.ai import AIPageContextInput, AIServerPageContext
from app.services.ai.guard_backend import GuardBackendDecision
from app.services.ai.pilot_guard import AIPilotGuard, AIPilotGuardError
from app.services.ai.postgres_guard_backend import PostgreSQLGuardBackend
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker


def _acquire(guard, settings):
    return guard.acquire(
        user=pilot_user(),
        settings=settings,
        input_chars=1,
        has_attachments=False,
        factory_id="huaxing",
    )


def test_two_instances_share_concurrency_rpm_and_daily_budget(shared_guard_runtime):
    backend, _sessions, _engine = shared_guard_runtime
    current = [datetime(2026, 8, 12, 8, 0, tzinfo=UTC)]
    api_guard = shared_guard(backend, instance_id="api:1", current=current)
    worker_guard = shared_guard(backend, instance_id="worker:1", current=current)
    settings = shared_settings(ai_pilot_requests_per_minute=2)

    api_lease = _acquire(api_guard, settings)
    with pytest.raises(AIPilotGuardError) as concurrent:
        _acquire(worker_guard, settings)
    assert concurrent.value.code == "AI_CONCURRENT_REQUEST_LIMIT"
    api_lease.mark_provider_started()
    api_lease.record_usage(11)
    api_lease.mark_completed()
    api_lease.close()

    worker_lease = _acquire(worker_guard, settings)
    worker_lease.close()
    with pytest.raises(AIPilotGuardError) as rate:
        _acquire(api_guard, settings)
    assert rate.value.code == "AI_RATE_LIMITED"
    assert rate.value.retry_after_seconds == 60
    assert api_guard.snapshot("user-pilot") == {
        "active_requests": 0,
        "requests_in_window": 2,
        "used_tokens": 11,
        "reserved_tokens": 0,
    }


def test_expired_lease_recovers_reservation_and_charges_started_provider(
    shared_guard_runtime,
):
    backend, _sessions, _engine = shared_guard_runtime
    current = [datetime(2026, 8, 12, 8, 0, tzinfo=UTC)]
    first_guard = shared_guard(backend, instance_id="api:leak", current=current)
    recovery_guard = shared_guard(
        backend,
        instance_id="worker:recovery",
        current=current,
    )
    settings = shared_settings(ai_pilot_requests_per_minute=10)
    leaked = _acquire(first_guard, settings)
    leaked.mark_provider_started()
    reservation = leaked.reservation_tokens

    current[0] += timedelta(seconds=settings.ai_guard_lease_seconds + 1)
    recovered = _acquire(recovery_guard, settings)
    recovered.close()
    snapshot = recovery_guard.snapshot("user-pilot")
    assert snapshot["active_requests"] == 0
    assert snapshot["reserved_tokens"] == 0
    assert snapshot["used_tokens"] == reservation


def test_asia_shanghai_budget_switch_is_shared_and_independent_by_day(
    shared_guard_runtime,
):
    backend, _sessions, _engine = shared_guard_runtime
    current = [datetime(2026, 8, 12, 15, 59, 59, tzinfo=UTC)]
    guard = shared_guard(backend, instance_id="api:day", current=current)
    base = shared_settings(ai_pilot_requests_per_minute=10)
    reservation = guard.reservation_tokens(
        input_chars=1,
        has_attachments=False,
        settings=base,
    )
    settings = shared_settings(
        ai_pilot_requests_per_minute=10,
        ai_pilot_daily_token_budget=reservation,
    )
    first = _acquire(guard, settings)
    first.mark_provider_started()
    first.mark_completed()
    first.close()
    with pytest.raises(AIPilotGuardError) as exceeded:
        _acquire(guard, settings)
    assert exceeded.value.code == "AI_BUDGET_EXCEEDED"

    current[0] += timedelta(seconds=2)
    next_day = _acquire(guard, settings)
    assert next_day.budget_day.isoformat() == "2026-08-13"
    next_day.close()


def test_disable_priority_and_explicit_pilot_deny_remain_fail_closed(
    shared_guard_runtime,
):
    backend, _sessions, _engine = shared_guard_runtime
    now = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
    guard = shared_guard(backend, instance_id="api:disable", current=[now])
    settings = shared_settings()

    for scope_type, scope_id in (
        ("USER", "user-pilot"),
        ("FACTORY", "huaxing"),
        ("GLOBAL", "ignored"),
    ):
        backend.set_disable_state(
            scope_type=scope_type,
            scope_id=scope_id,
            disabled=True,
            reason_code=f"TEST_{scope_type}",
            expires_at=None,
            instance_id="ops:test",
            now=now,
        )
    with pytest.raises(GuardBackendDecision) as disabled:
        backend.require_enabled(
            user_id="user-pilot",
            factory_id="huaxing",
            now=now,
        )
    assert disabled.value.disabled_scope == "GLOBAL"
    assert guard.evaluate_access(pilot_user(), settings).status == "DISABLED"

    with pytest.raises(AIPilotGuardError) as explicit_deny:
        guard.evaluate_access(
            pilot_user(user_id="not-a-pilot"),
            settings,
        )
    assert explicit_deny.value.code == "AI_PILOT_ACCESS_DENIED"


def test_factory_disable_is_checked_after_verified_factory_scope(
    shared_guard_runtime,
):
    backend, _sessions, _engine = shared_guard_runtime
    now = datetime(2026, 8, 12, 8, 0, tzinfo=UTC)
    guard = shared_guard(backend, instance_id="api:factory", current=[now])
    backend.set_disable_state(
        scope_type="FACTORY",
        scope_id="huaxing",
        disabled=True,
        reason_code="TEST_FACTORY",
        expires_at=None,
        instance_id="ops:test",
        now=now,
    )
    requested = AIPageContextInput(
        route_name="injection-scheduling-v2",
        path="/modules/production/injection-scheduling",
        factory_id="huaxing",
        module_id="injection-scheduling",
        selected_entity=None,
    )
    server = AIServerPageContext(
        verified_route_name="injection-scheduling-v2",
        verified_path="/modules/production/injection-scheduling",
        verified_factory_id="huaxing",
        verified_module_id="injection-scheduling",
        knowledge_id="injection-scheduling",
        allowed_tool_groups=("identity",),
    )
    with pytest.raises(AIPilotGuardError) as disabled:
        guard.require_factory_access(
            user=pilot_user(),
            requested_context=requested,
            server_context=server,
            settings=shared_settings(),
        )
    assert disabled.value.code == "AI_DISABLED"


def test_api_lease_binds_only_the_server_verified_factory(shared_guard_runtime):
    backend, sessions, _engine = shared_guard_runtime
    guard = shared_guard(
        backend,
        instance_id="api:verified-factory",
        current=[datetime(2026, 8, 12, 8, 0, tzinfo=UTC)],
    )
    lease = guard.acquire(
        user=pilot_user(),
        settings=shared_settings(ai_pilot_requests_per_minute=10),
        input_chars=1,
        has_attachments=False,
    )
    with sessions() as db:
        assert db.scalar(select(AIGuardLease.factory_id)) == ""
    lease.bind_factory("huaxing")
    with sessions() as db:
        assert db.scalar(select(AIGuardLease.factory_id)) == "huaxing"
    lease.close()


def test_cleanup_expires_leases_requests_budgets_and_temporary_disable_state(
    shared_guard_runtime,
):
    backend, _sessions, _engine = shared_guard_runtime
    current = [datetime(2026, 8, 1, 8, 0, tzinfo=UTC)]
    guard = shared_guard(backend, instance_id="api:cleanup", current=current)
    settings = shared_settings(
        ai_pilot_requests_per_minute=10,
        ai_guard_budget_retention_days=2,
    )
    completed = _acquire(guard, settings)
    completed.close()
    leaked = _acquire(guard, settings)
    leaked.mark_provider_started()
    backend.set_disable_state(
        scope_type="FACTORY",
        scope_id="huaxing",
        disabled=True,
        reason_code="TEMPORARY_TEST",
        expires_at=current[0] + timedelta(hours=1),
        instance_id="ops:test",
        now=current[0],
    )

    current[0] += timedelta(days=4)
    cleaned = backend.cleanup(
        now=current[0],
        budget_retention_days=settings.ai_guard_budget_retention_days,
    )
    assert cleaned == {
        "expired_leases": 1,
        "request_events": 2,
        "daily_budgets": 1,
        "disable_states": 1,
    }


def test_guard_lease_can_be_renewed_by_a_worker_heartbeat(shared_guard_runtime):
    backend, sessions, _engine = shared_guard_runtime
    current = [datetime(2026, 8, 12, 8, 0, tzinfo=UTC)]
    guard = shared_guard(backend, instance_id="worker:heartbeat", current=current)
    lease = _acquire(guard, shared_settings(ai_pilot_requests_per_minute=10))
    with sessions() as db:
        original_expiry = db.scalar(select(AIGuardLease.expires_at))
    current[0] += timedelta(seconds=60)
    lease.renew()
    with sessions() as db:
        renewed_expiry = db.scalar(select(AIGuardLease.expires_at))
    assert original_expiry is not None
    assert renewed_expiry is not None
    assert renewed_expiry > original_expiry
    lease.close()


def test_shared_guard_backend_is_wired_into_artifact_and_action_routes():
    from app.api.ai_actions import action_pilot_guard
    from app.api.ai_artifacts import artifact_pilot_guard

    assert action_pilot_guard._shared_backend is not None
    assert artifact_pilot_guard._shared_backend is not None


def test_shared_disable_interrupts_the_next_active_lease_heartbeat(
    shared_guard_runtime,
):
    backend, _sessions, _engine = shared_guard_runtime
    current = [datetime(2026, 8, 12, 8, 0, tzinfo=UTC)]
    guard = shared_guard(backend, instance_id="worker:disable", current=current)
    lease = _acquire(guard, shared_settings(ai_pilot_requests_per_minute=10))
    backend.set_disable_state(
        scope_type="GLOBAL",
        scope_id="ignored",
        disabled=True,
        reason_code="EMERGENCY_TEST",
        expires_at=None,
        instance_id="ops:test",
        now=current[0],
    )
    with pytest.raises(AIPilotGuardError) as disabled:
        lease.renew()
    assert disabled.value.code == "AI_DISABLED"
    lease.close()


def test_selected_shared_backend_refuses_sqlite_runtime_and_fails_closed(tmp_path):
    settings = Settings(
        _env_file=None,
        ai_enabled=True,
        ai_pilot_enabled=True,
        ai_pilot_user_ids="user-pilot",
        ai_pilot_factory_ids="huaxing",
        ai_shared_guard_enabled=True,
    )
    engine = create_engine(f"sqlite:///{(tmp_path / 'unsupported.db').as_posix()}")
    guard = AIPilotGuard(
        shared_backend=PostgreSQLGuardBackend(sessionmaker(bind=engine))
    )
    with pytest.raises(AIPilotGuardError) as unavailable:
        guard.evaluate_access(pilot_user(), settings)
    assert unavailable.value.code == "AI_GUARD_UNAVAILABLE"
    assert unavailable.value.status_code == 503
    assert unavailable.value.retryable is True
    engine.dispose()


def test_postgresql_backend_outage_is_mapped_to_fail_closed_guard_error():
    def unavailable_session():
        raise OperationalError("connect", {}, RuntimeError("database unavailable"))

    guard = AIPilotGuard(
        shared_backend=PostgreSQLGuardBackend(unavailable_session),
    )
    with pytest.raises(AIPilotGuardError) as unavailable:
        guard.evaluate_access(pilot_user(), shared_settings())
    assert unavailable.value.code == "AI_GUARD_UNAVAILABLE"
    assert unavailable.value.status_code == 503
    assert unavailable.value.retry_after_seconds == 5
