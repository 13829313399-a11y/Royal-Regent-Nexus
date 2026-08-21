from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
from app.core.config import Settings
from app.db import Base
from app.models.ai_action import AIActionConfirmation
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.ai_observability import AIEvalRun, AIFeedback, AIMetricEvent
from app.models.ai_task import AITask
from app.models.auth import AuthUser
from app.services.ai.observability.metrics import (
    AIObservabilityEvent,
    build_metric_summary,
    list_eval_runs,
    list_metric_events,
    record_metric_event,
    safe_record_metric_event,
)
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _session() -> Session:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(
        engine,
        tables=[
            AuthUser.__table__,
            AIConversation.__table__,
            AIMessage.__table__,
            AITask.__table__,
            AIActionConfirmation.__table__,
            AIFeedback.__table__,
            AIMetricEvent.__table__,
            AIEvalRun.__table__,
        ],
    )
    db = Session(engine)
    db.add(
        AuthUser(
            id="metric-user",
            username="metric-user",
            display_name="Metric User",
            password_salt="salt",
            password_hash="hash",
            status="active",
        )
    )
    db.commit()
    return db


def _task() -> AITask:
    return AITask(
        id="aitask-metric-0001",
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
        idempotency_key="task-metric-request-0001",
        request_hash="e" * 64,
        step_count=1,
        claim_count=2,
        created_at="2026-08-13T10:00:00+08:00",
        updated_at="2026-08-13T10:01:00+08:00",
        terminal_at="2026-08-13T10:01:00+08:00",
    )


def _action() -> AIActionConfirmation:
    return AIActionConfirmation(
        id="aiact-metric-0001",
        user_id="metric-user",
        tool_name="injection_scheduling.apply_preview",
        risk_level="CONSEQUENTIAL_WRITE",
        factory_id="huaxing",
        entity_type="schedule",
        entity_id="draft-0001",
        entity_revision=2,
        args_hash="f" * 64,
        normalized_action_json="{}",
        request_id="action-metric-request-0001",
        expires_at="2026-08-13T10:30:00+08:00",
        status="STALE",
        created_at="2026-08-13T10:00:00+08:00",
    )


def test_metadata_metrics_cover_model_tool_task_action_cost_and_eval_rates() -> None:
    db = _session()
    settings = Settings(
        _env_file=None,
        ai_observability_enabled=True,
        ai_input_token_cost_usd_per_million=2,
        ai_output_token_cost_usd_per_million=4,
    )
    try:
        db.add_all(
            [
                _task(),
                _action(),
                AIFeedback(
                    id="aifb-metric-0001",
                    owner_user_id="metric-user",
                    factory_id="huaxing",
                    target_type="RESPONSE",
                    target_id="request-metric-0001",
                    rating="NOT_HELPFUL",
                    issue_category="INCORRECT",
                    comment_text="结果需要人工纠正",
                    status="SUBMITTED",
                    idempotency_key="feedback-metric-0001",
                    reviewed_by=None,
                    review_note="",
                    eval_suite_id="",
                    eval_case_id="",
                    created_at="2026-08-13T10:00:00+08:00",
                    updated_at="2026-08-13T10:00:00+08:00",
                    reviewed_at="",
                ),
                AIEvalRun(
                    id="aiev-metric-0001",
                    suite_id="system_module_tutor_v1",
                    dataset_version="1.0.0",
                    dataset_hash="1" * 64,
                    runner_version="1.0.0",
                    mode="OFFLINE_FAKE",
                    skill_id="system.module_tutor",
                    skill_version="1.1.0",
                    skill_hash="2" * 64,
                    prompt_version="1.1.0",
                    prompt_hash="3" * 64,
                    provider="fake",
                    model="offline-fixture",
                    status="PASSED",
                    case_count=2,
                    passed_count=2,
                    failed_count=0,
                    metrics_json=json.dumps(
                        {
                            "grounded_claim_rate": 1.0,
                            "citation_accuracy": 1.0,
                            "tool_selection_precision": 1.0,
                            "tool_argument_accuracy": 1.0,
                            "unauthorized_action_rate": 0.0,
                            "cross_factory_leakage_rate": 0.0,
                            "preview_executed_mislabel_rate": 0.0,
                        }
                    ),
                    created_by="ci",
                    created_at="2026-08-13T10:00:00+08:00",
                    completed_at="2026-08-13T10:00:01+08:00",
                ),
            ]
        )
        db.commit()
        first = record_metric_event(
            db,
            AIObservabilityEvent(
                request_id="request-metric-0001",
                event_type="MODEL_RUN",
                event_key="terminal",
                owner_user_id="metric-user",
                factory_id="huaxing",
                task_id="aitask-metric-0001",
                action_id="aiact-metric-0001",
                skill_id="system.module_tutor",
                skill_version="1.1.0",
                skill_hash="2" * 64,
                prompt_version="1.1.0",
                prompt_hash="3" * 64,
                provider="qwen",
                model="qwen-test",
                status="SUCCESS",
                duration_ms=100,
                input_tokens=100,
                output_tokens=50,
                retry_count=1,
                evidence_count=2,
            ),
            settings=settings,
        )
        replay = record_metric_event(
            db,
            AIObservabilityEvent(
                request_id="request-metric-0001",
                event_type="MODEL_RUN",
                event_key="terminal",
                owner_user_id="metric-user",
                status="SUCCESS",
            ),
            settings=settings,
        )
        record_metric_event(
            db,
            AIObservabilityEvent(
                request_id="request-metric-0001",
                event_type="TOOL_CALL",
                event_key="tool:1",
                owner_user_id="metric-user",
                factory_id="huaxing",
                task_id="aitask-metric-0001",
                tool_name="knowledge.get_module_help",
                tool_version="1.0.0",
                status="FAILURE",
                duration_ms=25,
                error_code="AI_TOOL_TEMPORARY_FAILURE",
            ),
            settings=settings,
        )

        assert replay.id == first.id
        assert first.estimated_cost_microusd == 400
        summary = build_metric_summary(
            db,
            from_time="2026-08-01T00:00:00+08:00",
            to_time="2026-09-01T00:00:00+08:00",
        )

        assert summary.model_runs == 1
        assert summary.tool_calls == 1
        assert summary.tasks == 1
        assert summary.actions == 1
        assert summary.feedback_items == 1
        assert summary.eval_runs == 1
        assert summary.total_tokens == 150
        assert summary.estimated_cost_microusd == 400
        assert summary.cost_per_successful_task_microusd == 400
        assert summary.cost_basis == "CONFIGURED_ESTIMATE"
        assert summary.rates.task_success_rate == 1
        assert summary.rates.grounded_claim_rate == 1
        assert summary.rates.provider_retry_rate == 1
        assert summary.rates.model_failure_rate == 0
        assert summary.rates.tool_failure_rate == 1
        assert summary.rates.worker_retry_rate == 1
        assert summary.rates.user_correction_rate == 1
        assert summary.rates.unauthorized_action_rate == 0
        assert summary.rates.cross_factory_leakage_rate == 0
        assert summary.rates.preview_executed_mislabel_rate == 0
        assert summary.latency.model_run_p50_ms == 100
        assert summary.latency.model_run_p95_ms == 100
        assert summary.failures == {
            "provider": 0,
            "tool": 1,
            "worker": 0,
            "action": 1,
        }
        assert summary.raw_prompt_recorded is False
        assert summary.raw_tool_result_recorded is False
        assert summary.chain_of_thought_recorded is False

        exported = list_metric_events(
            db,
            from_time="2026-08-01T00:00:00+08:00",
            to_time="2026-09-01T00:00:00+08:00",
            limit=10,
            offset=0,
        )
        assert all(item.task_id == "aitask-metric-0001" for item in exported)
        tool_export = next(item for item in exported if item.event_type == "TOOL_CALL")
        assert tool_export.tool_version == "1.0.0"
        assert all(not hasattr(item, "owner_user_id") for item in exported)
        eval_export = list_eval_runs(
            db,
            from_time="2026-08-01T00:00:00+08:00",
            to_time="2026-09-01T00:00:00+08:00",
            limit=10,
            offset=0,
        )
        assert eval_export[0].dataset_hash == "1" * 64
        assert eval_export[0].skill_hash == "2" * 64
        assert eval_export[0].prompt_hash == "3" * 64
        assert eval_export[0].provider == "fake"
        assert eval_export[0].raw_cases_recorded is False
    finally:
        db.close()


def test_metric_model_has_no_raw_prompt_tool_result_or_chain_of_thought() -> None:
    columns = {item.name for item in AIMetricEvent.__table__.columns}
    assert not {
        "prompt",
        "raw_prompt",
        "tool_result",
        "raw_tool_result",
        "chain_of_thought",
        "reasoning_text",
    }.intersection(columns)


def test_safe_metric_recorder_never_breaks_ai_response() -> None:
    engine = create_engine("sqlite://", future=True)
    factory = sessionmaker(bind=engine, future=True)
    result = safe_record_metric_event(
        factory,
        AIObservabilityEvent(
            request_id="request-safe-recorder",
            event_type="MODEL_RUN",
            event_key="terminal",
            owner_user_id="missing-user",
            status="FAILURE",
        ),
        settings=Settings(_env_file=None, ai_observability_enabled=True),
    )
    assert result is None


def _run_alembic(
    database_url: str, *arguments: str
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(BACKEND_DIR / "alembic.ini"),
            *arguments,
        ],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_ai_observability_migration_and_protected_downgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "ai-observability.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = _run_alembic(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    engine = sa.create_engine(database_url)
    inspector = inspect(engine)
    assert {"ai_feedback", "ai_metric_events", "ai_eval_runs"} <= set(
        inspector.get_table_names()
    )
    metric_columns = {
        item["name"] for item in inspector.get_columns("ai_metric_events")
    }
    assert {"skill_hash", "prompt_hash", "retry_count", "estimated_cost_microusd"} <= (
        metric_columns
    )
    assert not {"raw_prompt", "raw_tool_result", "chain_of_thought"}.intersection(
        metric_columns
    )
    with engine.begin() as connection:
        assert (
            connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20260821_0082"
        )
        connection.execute(
            sa.text(
                "INSERT INTO ai_eval_runs (id, suite_id, dataset_version, "
                "dataset_hash, runner_version, mode, skill_id, skill_version, "
                "skill_hash, prompt_version, prompt_hash, status, created_at) "
                "VALUES ('aiev-protected', 'suite_v1', '1.0.0', :hash, '1.0.0', "
                "'OFFLINE_FAKE', 'system.module_tutor', '1.1.0', :hash, "
                "'1.1.0', :hash, 'PASSED', '2026-08-13T10:00:00+08:00')"
            ),
            {"hash": "a" * 64},
        )

    downgrade = _run_alembic(database_url, "downgrade", "20260813_0072")
    assert downgrade.returncode != 0
    assert "Refusing to downgrade 20260813_0073" in downgrade.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20260813_0073"
        )
