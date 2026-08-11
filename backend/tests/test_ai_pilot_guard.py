from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import Settings
from app.schemas.ai import AIPageContextInput, AIServerPageContext
from app.services.ai.pilot_guard import AIPilotGuard, AIPilotGuardError
from app.services.auth import AuthContext


def _settings(**overrides) -> Settings:
    values = {
        "app_env": "development",
        "ai_enabled": True,
        "ai_provider": "qwen",
        "ai_region": "cn-beijing",
        "ai_workspace_id": "ws-synthetic-pilot",
        "dashscope_api_key": "synthetic-test-key",
        "ai_default_model": "qwen3.7-plus",
        "ai_pilot_enabled": True,
        "ai_pilot_user_ids": "user-pilot",
        "ai_pilot_factory_ids": "huaxing",
        "ai_pilot_public_tls_verified": False,
        "ai_runtime_disable_path": "/app/backend/control/ai.disabled",
        "ai_pilot_max_concurrent_per_user": 1,
        "ai_pilot_requests_per_minute": 2,
        "ai_pilot_daily_token_budget": 10_000_000,
        "ai_pilot_max_output_tokens": 10,
        "ai_max_tool_rounds": 1,
        "ai_max_tool_result_bytes": 1,
        "ai_max_input_message_chars": 1,
        "ai_max_image_total_bytes": 100,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _user(
    *,
    user_id: str = "user-pilot",
    factory_scopes: tuple[str, ...] = ("huaxing",),
) -> AuthContext:
    return AuthContext(
        id=user_id,
        username=user_id,
        display_name="Pilot 合成用户",
        roles=("测试",),
        role_codes=("test",),
        permissions=frozenset(),
        factory_scopes=factory_scopes,
        department_scopes=(),
    )


def _page_context(factory_id: str | None) -> AIPageContextInput:
    return AIPageContextInput(
        route_name="injection-scheduling-v2",
        path="/modules/production/injection-scheduling",
        factory_id=factory_id,
        module_id="injection-scheduling",
        selected_entity=None,
    )


def _server_context(factory_id: str | None) -> AIServerPageContext:
    return AIServerPageContext(
        verified_route_name="injection-scheduling-v2",
        verified_path="/modules/production/injection-scheduling",
        verified_factory_id=factory_id,
        verified_module_id="injection-scheduling",
        knowledge_id="injection-scheduling",
        allowed_tool_groups=("identity", "module_knowledge"),
    )


def test_pilot_access_is_default_deny_and_production_requires_tls_assertion():
    guard = AIPilotGuard()
    user = _user()

    with pytest.raises(AIPilotGuardError) as disabled_non_pilot:
        guard.evaluate_access(
            _user(user_id="user-not-pilot"),
            _settings(ai_enabled=False),
        )
    assert disabled_non_pilot.value.code == "AI_PILOT_ACCESS_DENIED"

    disabled_pilot = guard.evaluate_access(user, _settings(ai_enabled=False))
    assert disabled_pilot.granted is False
    assert disabled_pilot.status == "DISABLED"

    with pytest.raises(AIPilotGuardError) as denied:
        guard.evaluate_access(user, _settings(ai_pilot_enabled=False))
    assert denied.value.code == "AI_PILOT_ACCESS_DENIED"
    assert denied.value.status_code == 403

    control_required = guard.evaluate_access(
        user,
        _settings(app_env="production", ai_runtime_disable_path=""),
    )
    assert control_required.status == "CONTROL_REQUIRED"
    wrong_control = guard.evaluate_access(
        user,
        _settings(
            app_env="production",
            ai_runtime_disable_path="/tmp/nonexistent-ai.disabled",
        ),
    )
    assert wrong_control.status == "CONTROL_REQUIRED"

    tls_required = guard.evaluate_access(
        user,
        _settings(app_env="production"),
    )
    assert tls_required.granted is False
    assert tls_required.status == "TLS_REQUIRED"
    granted = guard.evaluate_access(
        user,
        _settings(
            app_env="production",
            ai_pilot_public_tls_verified=True,
        ),
    )
    assert granted.granted is True
    assert granted.status == "GRANTED"
    assert granted.read_only is True


def test_runtime_disable_marker_is_immediate_and_content_is_never_read(tmp_path):
    marker = tmp_path / "ai.disabled"
    guard = AIPilotGuard()
    settings = _settings(ai_runtime_disable_path=str(marker))
    user = _user()

    assert guard.evaluate_access(user, settings).status == "GRANTED"
    marker.write_text("content-must-never-be-read", encoding="utf-8")
    access = guard.evaluate_access(user, settings)
    assert access.granted is False
    assert access.status == "DISABLED"
    with pytest.raises(AIPilotGuardError) as disabled:
        guard.acquire(
            user=user,
            settings=settings,
            input_chars=1,
            has_attachments=False,
        )
    assert disabled.value.code == "AI_DISABLED"
    marker.unlink()
    assert guard.evaluate_access(user, settings).status == "GRANTED"
    marker.mkdir()
    assert guard.evaluate_access(user, settings).status == "DISABLED"


def test_user_and_factory_scopes_are_both_required_including_null_context():
    guard = AIPilotGuard()
    settings = _settings()
    pilot_user = _user()

    assert guard.evaluate_access(pilot_user, settings).granted is True
    guard.require_factory_access(
        user=pilot_user,
        requested_context=None,
        server_context=None,
        settings=settings,
    )

    with pytest.raises(AIPilotGuardError):
        guard.evaluate_access(
            _user(factory_scopes=("huadeng",)),
            settings,
        )
    with pytest.raises(AIPilotGuardError):
        guard.require_factory_access(
            user=pilot_user,
            requested_context=_page_context("huadeng"),
            server_context=_server_context("huadeng"),
            settings=settings,
        )
    with pytest.raises(AIPilotGuardError):
        guard.require_factory_access(
            user=pilot_user,
            requested_context=_page_context("huaxing"),
            server_context=_server_context(None),
            settings=settings,
        )


def test_pilot_user_allowlist_admits_101_users_and_is_bounded_at_128():
    guard = AIPilotGuard()
    employee_ids = [f"user-employee-{index:03d}" for index in range(100)]
    superadmin_id = "user-superadmin"
    required_ids = [*employee_ids, superadmin_id]
    required_settings = _settings(ai_pilot_user_ids=",".join(required_ids))

    access = guard.evaluate_access(
        _user(user_id=superadmin_id, factory_scopes=("*",)),
        required_settings,
    )
    assert access.granted is True
    assert access.status == "GRANTED"

    maximum_ids = [f"user-capacity-{index:03d}" for index in range(128)]
    maximum_settings = _settings(
        ai_pilot_user_ids=f" , {', '.join(maximum_ids)},,",
    )
    assert guard.evaluate_access(
        _user(user_id=maximum_ids[-1]),
        maximum_settings,
    ).granted is True


@pytest.mark.parametrize(
    "configured_ids",
    [
        ",".join(f"user-over-{index:03d}" for index in range(129)),
        "user-duplicate,user-duplicate",
        "user-valid,user invalid",
        f"user-valid,{'x' * 129}",
    ],
)
def test_pilot_user_allowlist_fails_closed_for_invalid_configuration(
    configured_ids: str,
):
    guard = AIPilotGuard()
    first_id = configured_ids.split(",", 1)[0]

    with pytest.raises(AIPilotGuardError) as denied:
        guard.evaluate_access(
            _user(user_id=first_id),
            _settings(ai_pilot_user_ids=configured_ids),
        )

    assert denied.value.code == "AI_PILOT_ACCESS_DENIED"
    assert denied.value.status_code == 403


def test_pilot_factory_allowlist_remains_limited_to_canonical_factories():
    guard = AIPilotGuard()
    canonical_factories = (
        "huakang-a,huakang-b,huakang-c,huakang-d,huadeng,huaxing"
    )
    assert guard.evaluate_access(
        _user(factory_scopes=("*",)),
        _settings(ai_pilot_factory_ids=canonical_factories),
    ).granted is True

    with pytest.raises(AIPilotGuardError) as denied:
        guard.evaluate_access(
            _user(factory_scopes=("*",)),
            _settings(
                ai_pilot_factory_ids="huakang-a,unknown-factory",
            ),
        )

    assert denied.value.code == "AI_PILOT_ACCESS_DENIED"


def test_concurrency_limit_releases_and_cancelled_attempt_charges_reservation():
    guard = AIPilotGuard()
    settings = _settings(ai_pilot_requests_per_minute=10)
    user = _user()
    first = guard.acquire(
        user=user,
        settings=settings,
        input_chars=1,
        has_attachments=False,
    )

    with pytest.raises(AIPilotGuardError) as limited:
        guard.acquire(
            user=user,
            settings=settings,
            input_chars=1,
            has_attachments=False,
        )
    assert limited.value.code == "AI_CONCURRENT_REQUEST_LIMIT"
    assert limited.value.payload()["retry_after_seconds"] == 1

    first.mark_provider_started()
    reservation = first.reservation_tokens
    first.close()
    assert guard.snapshot(user.id) == {
        "active_requests": 0,
        "requests_in_window": 1,
        "used_tokens": reservation,
        "reserved_tokens": 0,
    }

    second = guard.acquire(
        user=user,
        settings=settings,
        input_chars=1,
        has_attachments=False,
    )
    second.close()


def test_minute_rate_limit_has_bounded_retry_and_expires():
    now = [100.0]
    guard = AIPilotGuard(clock=lambda: now[0])
    settings = _settings(ai_pilot_daily_token_budget=10_000_000)
    user = _user()
    for _ in range(2):
        lease = guard.acquire(
            user=user,
            settings=settings,
            input_chars=1,
            has_attachments=False,
        )
        lease.close()

    with pytest.raises(AIPilotGuardError) as limited:
        guard.acquire(
            user=user,
            settings=settings,
            input_chars=1,
            has_attachments=False,
        )
    assert limited.value.code == "AI_RATE_LIMITED"
    assert limited.value.retry_after_seconds == 60

    now[0] += 61
    lease = guard.acquire(
        user=user,
        settings=settings,
        input_chars=1,
        has_attachments=False,
    )
    lease.close()


def test_budget_reserves_all_tool_rounds_and_reconciles_fail_closed():
    current = [datetime(2026, 8, 11, 8, 0, tzinfo=UTC)]
    guard = AIPilotGuard(utcnow=lambda: current[0])
    settings = _settings()
    user = _user()
    reservation = guard.reservation_tokens(
        input_chars=1,
        has_attachments=False,
        settings=settings,
    )
    assert reservation == 163_882
    assert (
        guard.reservation_tokens(
            input_chars=1,
            has_attachments=True,
            settings=settings,
        )
        == 16_495
    )
    settings = _settings(ai_pilot_daily_token_budget=reservation + 4)

    first = guard.acquire(
        user=user,
        settings=settings,
        input_chars=1,
        has_attachments=False,
    )
    first.mark_provider_started()
    first.record_usage(5)
    first.mark_completed()
    first.close()
    assert guard.snapshot(user.id)["used_tokens"] == 5

    with pytest.raises(AIPilotGuardError) as exceeded:
        guard.acquire(
            user=user,
            settings=settings,
            input_chars=1,
            has_attachments=False,
        )
    assert exceeded.value.code == "AI_BUDGET_EXCEEDED"
    assert exceeded.value.retryable is True

    current[0] += timedelta(days=1)
    next_day = guard.acquire(
        user=user,
        settings=settings,
        input_chars=1,
        has_attachments=False,
    )
    next_day.close()


def test_completed_missing_usage_and_report_above_reservation_cannot_undercharge():
    guard = AIPilotGuard()
    settings = _settings(ai_pilot_daily_token_budget=10_000_000)
    user = _user()
    missing = guard.acquire(
        user=user,
        settings=settings,
        input_chars=1,
        has_attachments=False,
    )
    reservation = missing.reservation_tokens
    missing.mark_provider_started()
    missing.mark_completed()
    missing.close()
    assert guard.snapshot(user.id)["used_tokens"] == reservation

    above = guard.acquire(
        user=user,
        settings=settings,
        input_chars=1,
        has_attachments=False,
    )
    above.mark_provider_started()
    above.record_usage(reservation + 10)
    above.mark_completed()
    above.close()
    assert guard.snapshot(user.id)["used_tokens"] == (reservation * 2) + 10


def test_default_budget_admits_text_and_vision_and_small_usage_releases_reserve():
    guard = AIPilotGuard()
    settings = Settings(
        _env_file=None,
        ai_enabled=True,
        ai_pilot_enabled=True,
        ai_pilot_user_ids="user-pilot",
        ai_pilot_factory_ids="huaxing",
    )
    user = _user()
    text_reservation = guard.reservation_tokens(
        input_chars=10,
        has_attachments=False,
        settings=settings,
    )
    vision_reservation = guard.reservation_tokens(
        input_chars=10,
        has_attachments=True,
        settings=settings,
    )
    assert text_reservation < settings.ai_pilot_daily_token_budget
    assert vision_reservation < settings.ai_pilot_daily_token_budget

    text = guard.acquire(
        user=user,
        settings=settings,
        input_chars=10,
        has_attachments=False,
    )
    text.mark_provider_started()
    text.record_usage(25)
    text.mark_completed()
    text.close()
    assert guard.snapshot(user.id)["used_tokens"] == 25

    vision = guard.acquire(
        user=user,
        settings=settings,
        input_chars=10,
        has_attachments=True,
    )
    vision.close()
