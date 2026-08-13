from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from app.core.config import Settings
from app.db import Base
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.ai_guard import AIGuardDailyBudget
from app.models.ai_observability import AIMetricEvent
from app.models.ai_task import AITask
from app.models.auth import AuthUser, SystemNotification
from app.schemas.system import SystemNotificationUpdateRequest
from app.services.ai.observability.alerts import (
    AIAlertConfigurationError,
    AIAlertEvidenceError,
    build_ai_operational_alert_acknowledgement_report,
    ensure_ai_alert_runtime_ready,
    evaluate_ai_operational_alerts,
    probe_clamav_signature_age_hours,
)
from app.services.ai.observability.metrics import (
    AIObservabilityEvent,
    record_metric_event,
)
from app.services.auth import AuthContext
from app.services.system import update_system_notification
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session


def _settings(**updates: object) -> Settings:
    values: dict[str, object] = {
        "ai_operational_alerts_enabled": True,
        "ai_alert_target_user_ids": "alert-user",
        "ai_observability_enabled": True,
        "ai_metric_export_enabled": True,
        "ai_input_token_cost_usd_per_million": 2,
        "ai_output_token_cost_usd_per_million": 4,
        "ai_cost_per_successful_task_alert_microusd": 100,
        "ai_provider_failure_alert_count": 1,
        "ai_tool_failure_alert_count": 1,
        "ai_worker_recovery_alert_count": 1,
        "ai_budget_alert_percent": 80,
        "ai_scanner_signature_max_age_hours": 48,
        "ai_alert_window_minutes": 15,
        "ai_alert_cooldown_minutes": 60,
        "ai_artifacts_enabled": True,
        "ai_artifact_scanner_backend": "clamav",
        "ai_pilot_daily_token_budget": 100,
    }
    values.update(updates)
    return Settings(_env_file=None, **values)


def _session() -> Session:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            AuthUser.__table__,
            SystemNotification.__table__,
            AIConversation.__table__,
            AIMessage.__table__,
            AITask.__table__,
            AIMetricEvent.__table__,
            AIGuardDailyBudget.__table__,
        ],
    )
    db = Session(engine)
    db.add_all(
        [
            AuthUser(
                id="alert-user",
                username="alert-user",
                display_name="Alert User",
                password_salt="salt",
                password_hash="hash",
                status="active",
            ),
            AuthUser(
                id="metric-user",
                username="metric-user",
                display_name="Metric User",
                password_salt="salt",
                password_hash="hash",
                status="active",
            ),
        ]
    )
    db.commit()
    return db


def _task() -> AITask:
    timestamp = "2026-08-13T11:59:00+08:00"
    return AITask(
        id="aitask-alert-0001",
        owner_user_id="metric-user",
        conversation_id=None,
        input_message_id=None,
        factory_scope="huaxing",
        task_type="READ",
        state="COMPLETED",
        maximum_risk="READ_ONLY",
        primary_skill_id="system.module_tutor",
        primary_skill_version="1.1.0",
        primary_skill_hash="a" * 64,
        prompt_version="1.1.0",
        prompt_hash="b" * 64,
        runtime_plan_json="{}",
        runtime_plan_hash="c" * 64,
        server_page_context_json="null",
        tool_versions_json="{}",
        required_access_json="[]",
        input_hash="d" * 64,
        idempotency_key="task-alert-request-0001",
        request_hash="e" * 64,
        step_count=1,
        claim_count=2,
        created_at=timestamp,
        updated_at=timestamp,
        terminal_at=timestamp,
    )


def _record_alert_metrics(db: Session, settings: Settings) -> None:
    record_metric_event(
        db,
        AIObservabilityEvent(
            request_id="request-alert-success-0001",
            event_type="MODEL_RUN",
            event_key="terminal",
            owner_user_id="metric-user",
            task_id="aitask-alert-0001",
            status="SUCCESS",
            input_tokens=100,
            output_tokens=50,
        ),
        settings=settings,
    )
    record_metric_event(
        db,
        AIObservabilityEvent(
            request_id="request-alert-provider-0001",
            event_type="MODEL_RUN",
            event_key="terminal",
            owner_user_id="metric-user",
            task_id="aitask-alert-0001",
            status="FAILURE",
            error_code="AI_PROVIDER_UNAVAILABLE",
        ),
        settings=settings,
    )
    record_metric_event(
        db,
        AIObservabilityEvent(
            request_id="request-alert-tool-0001",
            event_type="TOOL_CALL",
            event_key="tool:1",
            owner_user_id="metric-user",
            task_id="aitask-alert-0001",
            status="FAILURE",
            error_code="AI_TOOL_TEMPORARY_FAILURE",
        ),
        settings=settings,
    )


def test_all_six_alerts_are_idempotent_metadata_notifications_and_can_be_acknowledged(
    monkeypatch,
) -> None:
    db = _session()
    settings = _settings()
    current = datetime(
        2026,
        8,
        13,
        12,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )
    monkeypatch.setattr(
        "app.services.ai.observability.metrics.business_now",
        lambda: current,
    )
    try:
        db.add(_task())
        db.add(
            AIGuardDailyBudget(
                user_id="metric-user",
                budget_day=current.date().isoformat(),
                used_tokens=90,
                reserved_tokens=0,
                updated_at=current.isoformat(timespec="seconds"),
            )
        )
        db.commit()
        _record_alert_metrics(db, settings)

        first = evaluate_ai_operational_alerts(
            db,
            settings=settings,
            now=current,
            scanner_age_probe=lambda _: 49,
        )
        assert {item.alert_type for item in first.items if item.triggered} == {
            "COST_PER_SUCCESSFUL_TASK",
            "PROVIDER_FAILURE",
            "TOOL_FAILURE",
            "WORKER_RECOVERY",
            "SCANNER_STALE",
            "BUDGET",
        }
        assert first.recipient_count == 1
        assert all(len(item.notification_ids) == 1 for item in first.items)
        assert db.scalar(select(func.count()).select_from(SystemNotification)) == 6

        replay = evaluate_ai_operational_alerts(
            db,
            settings=settings,
            now=current,
            scanner_age_probe=lambda _: 49,
        )
        assert replay == first
        assert db.scalar(select(func.count()).select_from(SystemNotification)) == 6

        notifications = list(db.scalars(select(SystemNotification)).all())
        assert all(item.type == "ai_operational_alert" for item in notifications)
        assert all(item.target_user_id == "alert-user" for item in notifications)
        assert all("prompt" not in item.payload_json.lower() for item in notifications)
        assert all(
            "tool_result" not in item.payload_json.lower() for item in notifications
        )
        assert all(
            "customer" not in item.payload_json.lower() for item in notifications
        )

        notification_ids = tuple(item.id for item in notifications)
        pending_report = build_ai_operational_alert_acknowledgement_report(
            db,
            notification_ids=notification_ids,
            now=current,
        )
        assert pending_report.notification_count == 6
        assert pending_report.recipient_count == 1
        assert pending_report.complete_delivery_set is True
        assert pending_report.all_acknowledged is False
        assert all(not item.acknowledged for item in pending_report.items)
        assert all(not hasattr(item, "target_user_id") for item in pending_report.items)
        assert all(not hasattr(item, "observed_value") for item in pending_report.items)

        partial_report = build_ai_operational_alert_acknowledgement_report(
            db,
            notification_ids=(notification_ids[0],),
            now=current,
        )
        assert partial_report.complete_delivery_set is False
        assert partial_report.all_acknowledged is False

        alert_user = AuthContext(
            id="alert-user",
            username="alert-user",
            display_name="Alert User",
            roles=("运维",),
            role_codes=("operations",),
            permissions=frozenset(),
            factory_scopes=("huaxing",),
            department_scopes=("system",),
        )
        for notification in notifications:
            acknowledged = update_system_notification(
                db,
                alert_user,
                notification.id,
                SystemNotificationUpdateRequest(status="handled"),
            )
            assert acknowledged.status == "handled"
            assert acknowledged.read_at
            assert acknowledged.handled_at

        acknowledged_report = build_ai_operational_alert_acknowledgement_report(
            db,
            notification_ids=notification_ids,
            now=current,
        )
        assert acknowledged_report.complete_delivery_set is True
        assert acknowledged_report.all_acknowledged is True
        assert all(item.acknowledged for item in acknowledged_report.items)
    finally:
        db.close()


def test_acknowledgement_report_fails_closed_for_missing_or_tampered_alerts() -> None:
    db = _session()
    notification_id = f"ainotif-{'a' * 40}"
    try:
        with pytest.raises(AIAlertEvidenceError):
            build_ai_operational_alert_acknowledgement_report(
                db,
                notification_ids=(notification_id,),
            )

        db.add(
            SystemNotification(
                id=notification_id,
                target_user_id="alert-user",
                target_permission="",
                target_factory_id="",
                target_department="",
                type="ai_operational_alert",
                title="篡改告警",
                message="metadata only",
                payload_json='{"metadata_only":true}',
                status="handled",
                created_at="2026-08-13T12:00:00+08:00",
                read_at="2026-08-13T12:01:00+08:00",
                handled_at="2026-08-13T12:02:00+08:00",
            )
        )
        db.commit()
        with pytest.raises(AIAlertEvidenceError):
            build_ai_operational_alert_acknowledgement_report(
                db,
                notification_ids=(notification_id,),
            )
    finally:
        db.close()


def test_alerting_fails_closed_when_required_channel_or_rates_are_missing() -> None:
    with pytest.raises(AIAlertConfigurationError) as missing:
        ensure_ai_alert_runtime_ready(
            _settings(
                ai_alert_target_user_ids="",
                ai_input_token_cost_usd_per_million=0,
                ai_artifact_scanner_backend="disabled",
            )
        )
    message = str(missing.value)
    assert "target_users" in message
    assert "approved_token_rates" in message
    assert "clamav_scanner" in message


def test_fractional_observations_do_not_trigger_before_approved_thresholds(
    monkeypatch,
) -> None:
    db = _session()
    settings = _settings(
        ai_pilot_daily_token_budget=1000,
        ai_budget_alert_percent=80,
        ai_scanner_signature_max_age_hours=48,
        ai_input_token_cost_usd_per_million=1,
        ai_output_token_cost_usd_per_million=1,
        ai_cost_per_successful_task_alert_microusd=100,
    )
    current = datetime(
        2026,
        8,
        13,
        12,
        0,
        tzinfo=timezone(timedelta(hours=8)),
    )
    monkeypatch.setattr(
        "app.services.ai.observability.metrics.business_now",
        lambda: current,
    )
    try:
        first_task = _task()
        first_task.id = "aitask-fractional-cost-1"
        first_task.idempotency_key = "fractional-cost-1"
        first_task.request_hash = "f" * 64
        first_task.claim_count = 1
        second_task = _task()
        second_task.id = "aitask-fractional-cost-2"
        second_task.idempotency_key = "fractional-cost-2"
        second_task.request_hash = "1" * 64
        second_task.claim_count = 1
        db.add_all([first_task, second_task])
        db.add(
            AIGuardDailyBudget(
                user_id="metric-user",
                budget_day=current.date().isoformat(),
                used_tokens=799,
                reserved_tokens=0,
                updated_at=current.isoformat(timespec="seconds"),
            )
        )
        db.commit()
        for index, (task_id, input_tokens) in enumerate(
            (
                (first_task.id, 99),
                (second_task.id, 100),
            ),
            start=1,
        ):
            record_metric_event(
                db,
                AIObservabilityEvent(
                    request_id=f"request-fractional-cost-{index}",
                    event_type="MODEL_RUN",
                    event_key="model:1",
                    owner_user_id="metric-user",
                    task_id=task_id,
                    status="SUCCESS",
                    input_tokens=input_tokens,
                ),
                settings=settings,
            )

        evaluation = evaluate_ai_operational_alerts(
            db,
            settings=settings,
            now=current,
            scanner_age_probe=lambda _: 47.999,
        )
        by_type = {item.alert_type: item for item in evaluation.items}

        assert by_type["COST_PER_SUCCESSFUL_TASK"].observed_value == 99
        assert by_type["COST_PER_SUCCESSFUL_TASK"].triggered is False
        assert by_type["SCANNER_STALE"].observed_value == 47
        assert by_type["SCANNER_STALE"].triggered is False
        assert by_type["BUDGET"].observed_value == 79
        assert by_type["BUDGET"].triggered is False
        assert db.scalar(select(func.count()).select_from(SystemNotification)) == 0
    finally:
        db.close()


def test_clamav_version_probe_returns_signature_age_without_exposing_response(
    monkeypatch,
) -> None:
    class FakeSocket:
        sent = b""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def settimeout(self, _timeout: float) -> None:
            return None

        def sendall(self, payload: bytes) -> None:
            self.sent = payload

        def recv(self, _size: int) -> bytes:
            return b"ClamAV 1.4.3/27901/Thu Aug 13 02:00:00 2026\0"

    fake = FakeSocket()
    monkeypatch.setattr(
        "app.services.ai.observability.alerts.socket.create_connection",
        lambda *_args, **_kwargs: fake,
    )
    age = probe_clamav_signature_age_hours(
        _settings(),
        now=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc),
    )
    assert age == 10
    assert fake.sent == b"zVERSION\0"
