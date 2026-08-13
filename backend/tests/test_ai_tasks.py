from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import app.api.ai_tasks as ai_tasks_api
import pytest
from app.core.config import Settings, settings
from app.db import Base, get_db
from app.main import app
from app.models.ai_action import AIActionConfirmation
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.ai_task import AITask, AITaskEvent, AITaskStep
from app.models.auth import AuthAuditLog, AuthUser
from app.schemas.ai.context import AIServerPageContext
from app.schemas.ai.task import (
    AITaskCreate,
    AITaskEventType,
    AITaskState,
    AITaskStepCreate,
    AITaskStepState,
    AITaskType,
)
from app.schemas.ai.tool import AIToolRiskLevel
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.task_events import append_task_event, read_task_events
from app.services.ai.task_service import (
    AITaskConflictError,
    AITaskNotFoundError,
    AITaskResumeError,
    create_task,
    enforce_task_retention,
    get_owned_task,
    request_task_cancellation,
    request_task_resume,
    task_data,
    transition_step,
    transition_task,
)
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.auth import (
    AuthContext,
    AuthGrantContext,
    AuthOverrideContext,
    get_current_user,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="sqlite://",
        ai_enabled=True,
        ai_pilot_enabled=True,
        ai_pilot_user_ids="owner,other",
        ai_pilot_factory_ids="huaxing",
        ai_provider="fake",
        ai_nif_runtime_enabled=True,
        ai_skill_router_enabled=True,
        ai_evidence_v1_enabled=True,
        ai_tasks_enabled=True,
    )


def _user(
    user_id: str = "owner",
    *,
    factories: tuple[str, ...] = ("huaxing",),
    permission: str | None = None,
    deny: bool = False,
) -> AuthContext:
    permissions = frozenset({permission}) if permission else frozenset()
    grants = tuple(
        AuthGrantContext(
            role_id=f"role-{user_id}-{factory}",
            role_name="AI 任务测试",
            role_code="ai-task-test",
            factory_id=factory,
            department="production",
            permissions=permissions,
            binding_id=f"binding-{user_id}-{factory}",
        )
        for factory in factories
    )
    overrides = (
        (
            AuthOverrideContext(
                id="deny-task-test",
                permission_code=permission or "",
                effect="deny",
                factory_id="huaxing",
                department="production",
            ),
        )
        if deny
        else ()
    )
    return AuthContext(
        id=user_id,
        username=user_id,
        display_name=user_id,
        roles=("AI 任务测试",),
        role_codes=("ai-task-test",),
        permissions=permissions,
        factory_scopes=factories,
        department_scopes=("production",),
        grants=grants,
        overrides=overrides,
    )


def _enable_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _prepare_engine(engine: Engine) -> None:
    _enable_foreign_keys(engine)
    Base.metadata.create_all(
        engine,
        tables=[
            AuthUser.__table__,
            AuthAuditLog.__table__,
            AIActionConfirmation.__table__,
            AIConversation.__table__,
            AIMessage.__table__,
            AITask.__table__,
            AITaskStep.__table__,
            AITaskEvent.__table__,
        ],
    )
    with Session(engine) as db:
        for user_id in ("owner", "other"):
            db.add(
                AuthUser(
                    id=user_id,
                    username=user_id,
                    display_name=user_id,
                    password_salt="salt",
                    password_hash="hash",
                    status="active",
                    force_password_change=0,
                    avatar_png=None,
                    avatar_version="",
                    last_login_at="",
                    created_at="2026-08-12T08:00:00+08:00",
                    updated_at="2026-08-12T08:00:00+08:00",
                )
            )
        db.commit()


def _database() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    _prepare_engine(engine)
    return Session(engine)


def _payload(
    *,
    idempotency_key: str = "task-request-owner-1",
    input_hash: str = "a" * 64,
) -> AITaskCreate:
    return AITaskCreate(
        task_type=AITaskType.READ,
        factory_scope="huaxing",
        primary_skill_id="system.module_tutor",
        proposed_tool_names=("identity.get_current_context",),
        proposed_max_steps=1,
        input_hash=input_hash,
        idempotency_key=idempotency_key,
        steps=(
            AITaskStepCreate(
                key="read_context",
                kind=AITaskType.READ,
                label="读取当前身份上下文",
                tool_name="identity.get_current_context",
            ),
        ),
    )


def _create(db: Session, *, payload: AITaskCreate | None = None) -> AITask:
    registry = build_default_tool_registry(controlled_apply_enabled=False)
    return create_task(
        db,
        payload=payload or _payload(),
        user=_user(),
        settings=_settings(),
        registry=registry,
        skill_registry=SkillRegistry(registry),
        server_page_context=None,
        allowed_factory_scopes=frozenset({"huaxing"}),
        request_id="test-request",
    )


def _advance_to_running(db: Session, task: AITask) -> None:
    for state in (AITaskState.UNDERSTOOD, AITaskState.RUNNING):
        transition_task(
            db,
            task=task,
            requested_state=state,
            actor_type="SYSTEM",
            reason_code=f"TASK_{state.value}",
            settings=_settings(),
        )


def test_task_persists_across_sessions_and_create_is_idempotent() -> None:
    db = _database()
    try:
        task = _create(db)
        replay = _create(db)
        assert replay.id == task.id
        assert db.scalar(select(func.count(AITask.id))) == 1
        assert db.scalar(select(func.count(AITaskStep.id))) == 1
        assert db.scalar(select(func.count(AITaskEvent.id))) == 1

        with pytest.raises(AITaskConflictError):
            _create(db, payload=_payload(input_hash="b" * 64))

        task_id = task.id
        engine = db.get_bind()
        db.close()
        db = Session(engine)
        recovered = get_owned_task(
            db,
            task_id=task_id,
            user=_user(),
            allowed_factory_scopes=frozenset({"huaxing"}),
        )
        response = task_data(db, recovered)
        assert response.id == task_id
        assert response.state is AITaskState.CREATED
        assert response.runtime_plan.allowed_tool_names == (
            "identity.get_current_context",
        )
    finally:
        db.close()


def test_task_storage_contains_hashes_and_metadata_but_no_raw_input() -> None:
    db = _database()
    try:
        _create(db)
        dump = "\n".join(
            str(row)
            for table in ("ai_tasks", "ai_task_steps", "ai_task_events")
            for row in db.execute(text(f"SELECT * FROM {table}")).all()
        )
        assert "password: should-never-be-stored" not in dump
        assert "a" * 64 in dump
        event_record = db.scalar(select(AITaskEvent))
        assert event_record is not None
        assert not hasattr(event_record, "payload_json")
        assert json.loads(event_record.evidence_json) == []
        assert json.loads(event_record.artifact_refs_json) == []
    finally:
        db.close()


def test_cross_user_factory_loss_and_explicit_deny_are_not_found() -> None:
    db = _database()
    try:
        task = _create(db)
        for user in (_user("other"), _user(factories=())):
            with pytest.raises(AITaskNotFoundError):
                get_owned_task(
                    db,
                    task_id=task.id,
                    user=user,
                    allowed_factory_scopes=frozenset({"huaxing"}),
                )

        permission = "injection_scheduling:read"
        task.required_access_json = json.dumps(
            [
                {
                    "tool_name": "test.read",
                    "permission": permission,
                    "departments": ["production"],
                }
            ]
        )
        db.commit()
        allowed = _user(permission=permission)
        assert (
            get_owned_task(
                db,
                task_id=task.id,
                user=allowed,
                allowed_factory_scopes=frozenset({"huaxing"}),
            ).id
            == task.id
        )
        with pytest.raises(AITaskNotFoundError):
            get_owned_task(
                db,
                task_id=task.id,
                user=_user(permission=permission, deny=True),
                allowed_factory_scopes=frozenset({"huaxing"}),
            )
    finally:
        db.close()


def test_cancellation_is_an_audited_intent_and_replay_is_stable() -> None:
    db = _database()
    try:
        task = _create(db)
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.UNDERSTOOD,
            actor_type="SYSTEM",
            reason_code="TASK_UNDERSTOOD",
            settings=_settings(),
        )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.PLANNED,
            actor_type="SYSTEM",
            reason_code="TASK_PLANNED",
            settings=_settings(),
        )
        db.commit()
        revision = task.revision
        request_task_cancellation(
            db,
            task=task,
            user=_user(),
            expected_revision=revision,
            reason_code="USER_CANCELLED",
            settings=_settings(),
        )
        event_count = db.scalar(select(func.count(AITaskEvent.id)))
        assert task.state == AITaskState.CANCELLING.value
        assert task.cancellation_requested_at

        request_task_cancellation(
            db,
            task=task,
            user=_user(),
            expected_revision=revision,
            reason_code="USER_CANCELLED",
            settings=_settings(),
        )
        assert db.scalar(select(func.count(AITaskEvent.id))) == event_count
        assert task.state != AITaskState.CANCELLED.value
    finally:
        db.close()


def test_failed_task_resume_revalidates_and_only_retries_idempotent_steps() -> None:
    db = _database()
    registry = build_default_tool_registry(controlled_apply_enabled=False)
    try:
        task = _create(db)
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task.id))
        assert step is not None
        _advance_to_running(db, task)
        transition_step(
            db,
            task=task,
            step=step,
            requested_state=AITaskStepState.RUNNING,
            actor_type="SYSTEM",
            reason_code="STEP_RUNNING",
        )
        transition_step(
            db,
            task=task,
            step=step,
            requested_state=AITaskStepState.FAILED,
            actor_type="SYSTEM",
            reason_code="STEP_FAILED",
            failure_code="TOOL_TIMEOUT",
        )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.FAILED,
            actor_type="SYSTEM",
            reason_code="TASK_FAILED",
            failure_code="TOOL_TIMEOUT",
            settings=_settings(),
        )
        db.commit()

        request_task_resume(
            db,
            task=task,
            user=_user(),
            expected_revision=task.revision,
            expected_input_hash=task.input_hash,
            expected_runtime_plan_hash=task.runtime_plan_hash,
            registry=registry,
            skill_registry=SkillRegistry(registry),
            settings=_settings(),
        )
        assert task.state == AITaskState.RETRY_PENDING.value
        assert step.state == AITaskStepState.RETRY_PENDING.value
        assert task.retention_expires_at == ""

        transition_task(
            db,
            task=task,
            requested_state=AITaskState.RUNNING,
            actor_type="SYSTEM",
            reason_code="TASK_RETRY_RUNNING",
            settings=_settings(),
        )
        transition_step(
            db,
            task=task,
            step=step,
            requested_state=AITaskStepState.RUNNING,
            actor_type="SYSTEM",
            reason_code="STEP_RETRY_RUNNING",
        )
        transition_step(
            db,
            task=task,
            step=step,
            requested_state=AITaskStepState.FAILED,
            actor_type="SYSTEM",
            reason_code="STEP_FAILED_AGAIN",
            failure_code="TOOL_TIMEOUT",
        )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.FAILED,
            actor_type="SYSTEM",
            reason_code="TASK_FAILED_AGAIN",
            failure_code="TOOL_TIMEOUT",
            settings=_settings(),
        )
        step.idempotent = 0
        db.commit()
        with pytest.raises(AITaskResumeError):
            request_task_resume(
                db,
                task=task,
                user=_user(),
                expected_revision=task.revision,
                expected_input_hash=task.input_hash,
                expected_runtime_plan_hash=task.runtime_plan_hash,
                registry=registry,
                skill_registry=SkillRegistry(registry),
                settings=_settings(),
            )
    finally:
        db.close()


def test_resume_rejects_access_and_freshness_changes() -> None:
    db = _database()
    registry = build_default_tool_registry(controlled_apply_enabled=False)
    try:
        task = _create(db)
        _advance_to_running(db, task)
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.WAITING_INPUT,
            actor_type="SYSTEM",
            reason_code="TASK_WAITING_INPUT",
            settings=_settings(),
        )
        db.commit()
        with pytest.raises(AITaskResumeError):
            request_task_resume(
                db,
                task=task,
                user=_user(),
                expected_revision=task.revision,
                expected_input_hash="f" * 64,
                expected_runtime_plan_hash=task.runtime_plan_hash,
                registry=registry,
                skill_registry=SkillRegistry(registry),
                settings=_settings(),
            )

        task.required_access_json = json.dumps(
            [
                {
                    "tool_name": "test.read",
                    "permission": "injection_scheduling:read",
                    "departments": ["production"],
                }
            ]
        )
        db.commit()
        with pytest.raises(AITaskNotFoundError):
            request_task_resume(
                db,
                task=task,
                user=_user(),
                expected_revision=task.revision,
                expected_input_hash=task.input_hash,
                expected_runtime_plan_hash=task.runtime_plan_hash,
                registry=registry,
                skill_registry=SkillRegistry(registry),
                settings=_settings(),
            )
    finally:
        db.close()


def test_preview_task_records_preview_state_without_creating_an_action() -> None:
    db = _database()
    registry = build_default_tool_registry(controlled_apply_enabled=False)
    try:
        base_user = _user(permission="injection_scheduling:read")
        permissions = frozenset(
            {"injection_scheduling:read", "injection_scheduling:edit"}
        )
        user = replace(
            base_user,
            permissions=permissions,
            grants=(replace(base_user.grants[0], permissions=permissions),),
        )
        context = AIServerPageContext(
            verified_route_name="injection-scheduling-v2",
            verified_path="/modules/production/injection-scheduling",
            verified_factory_id="huaxing",
            verified_module_id="injection-scheduling",
            knowledge_id="injection-scheduling",
            allowed_tool_groups=(
                "identity",
                "module_knowledge",
                "injection_scheduling",
            ),
        )
        task = create_task(
            db,
            payload=AITaskCreate(
                task_type=AITaskType.PREVIEW,
                factory_scope="huaxing",
                primary_skill_id="injection_scheduling.preview_advisor",
                proposed_tool_names=("injection_scheduling.generate_preview",),
                proposed_max_steps=1,
                proposed_maximum_risk=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
                input_hash="9" * 64,
                idempotency_key="preview-task-owner-1",
                steps=(
                    AITaskStepCreate(
                        key="generate_preview",
                        kind=AITaskType.PREVIEW,
                        label="生成候选方案",
                        tool_name="injection_scheduling.generate_preview",
                    ),
                ),
            ),
            user=user,
            settings=_settings(),
            registry=registry,
            skill_registry=SkillRegistry(registry),
            server_page_context=context,
            allowed_factory_scopes=frozenset({"huaxing"}),
            request_id="preview-test-request",
        )
        step = db.scalar(select(AITaskStep).where(AITaskStep.task_id == task.id))
        assert step is not None
        assert step.side_effect_class == "PREVIEW_STATE"
        assert step.idempotent == 0
        assert db.scalar(select(func.count(AIActionConfirmation.id))) == 0
    finally:
        db.close()


def test_event_sequence_is_atomic_under_concurrent_writers(tmp_path: Path) -> None:
    database_path = tmp_path / "task-events.db"
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )
    _prepare_engine(engine)
    with Session(engine) as db:
        task_id = _create(db).id

    def write_event(index: int) -> None:
        with Session(engine) as worker_db:
            task = worker_db.get(AITask, task_id)
            assert task is not None
            append_task_event(
                worker_db,
                task=task,
                event_type=AITaskEventType.STATE_TRANSITION,
                actor_type="SYSTEM",
                reason_code=f"CONCURRENT_EVENT_{index}",
            )
            worker_db.commit()

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write_event, range(8)))

    with Session(engine) as db:
        sequences = list(
            db.scalars(
                select(AITaskEvent.sequence)
                .where(AITaskEvent.task_id == task_id)
                .order_by(AITaskEvent.sequence)
            ).all()
        )
        assert sequences == list(range(1, 10))
        first_page = read_task_events(db, task_id=task_id, limit=3)
        assert [item.sequence for item in first_page.items] == [1, 2, 3]
        assert first_page.next_after == 3
        second_page = read_task_events(
            db,
            task_id=task_id,
            after=first_page.next_after,
            limit=100,
        )
        assert [item.sequence for item in second_page.items] == list(range(4, 10))


def test_terminal_retention_cascades_and_security_audit_has_its_own_window() -> None:
    db = _database()
    try:
        started = datetime(2026, 1, 1, tzinfo=UTC)
        task = _create(db)
        _advance_to_running(db, task)
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.FAILED,
            actor_type="SYSTEM",
            reason_code="TASK_FAILED",
            failure_code="TEST_FAILURE",
            settings=_settings(),
            now=started,
        )
        db.add_all(
            [
                AuthAuditLog(
                    user_id="owner",
                    username="owner",
                    action="ai_task_access_denied",
                    detail="operation=detail",
                    created_at="2025-01-01 00:00:00",
                ),
                AuthAuditLog(
                    user_id="owner",
                    username="owner",
                    action="login_success",
                    detail="unrelated",
                    created_at="2025-01-01 00:00:00",
                ),
            ]
        )
        db.commit()
        assert datetime.fromisoformat(task.retention_expires_at) == started + timedelta(
            days=180
        )
        assert datetime.fromisoformat(task.backup_delete_by) == started + timedelta(
            days=210
        )

        deleted_tasks, deleted_audits = enforce_task_retention(
            db,
            settings=_settings(),
            now=started + timedelta(days=181),
        )
        assert (deleted_tasks, deleted_audits) == (1, 1)
        assert db.scalar(select(func.count(AITask.id))) == 0
        assert db.scalar(select(func.count(AITaskStep.id))) == 0
        assert db.scalar(select(func.count(AITaskEvent.id))) == 0
        assert db.scalar(select(func.count(AuthAuditLog.id))) == 1
    finally:
        db.close()


def test_task_api_is_default_off_and_exposes_bounded_lifecycle(monkeypatch) -> None:
    db = _database()
    user_holder = {"value": _user()}

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user_holder["value"]
    for name, value in (
        ("ai_enabled", True),
        ("ai_pilot_enabled", True),
        ("ai_pilot_user_ids", "owner,other"),
        ("ai_pilot_factory_ids", "huaxing"),
        ("ai_runtime_disable_path", ""),
        ("app_env", "development"),
        ("ai_nif_runtime_enabled", True),
        ("ai_skill_router_enabled", True),
        ("ai_evidence_v1_enabled", True),
    ):
        monkeypatch.setattr(settings, name, value)
    try:
        client = TestClient(app)
        monkeypatch.setattr(settings, "ai_tasks_enabled", False)
        assert (
            client.post(
                "/api/ai/tasks", json=_payload().model_dump(mode="json")
            ).status_code
            == 404
        )

        monkeypatch.setattr(settings, "ai_tasks_enabled", True)
        monkeypatch.setattr(settings, "ai_task_worker_enabled", False)
        worker_capability = client.get("/api/ai/tasks/capabilities")
        assert worker_capability.status_code == 200
        assert worker_capability.json() == {
            "contract_version": "1",
            "available": False,
            "worker_enabled": False,
        }
        monkeypatch.setattr(settings, "ai_task_worker_enabled", True)
        assert client.get("/api/ai/tasks/capabilities").json()["available"] is True
        created = client.post(
            "/api/ai/tasks",
            json=_payload(idempotency_key="api-task-owner-1").model_dump(mode="json"),
        )
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        assert client.get(f"/api/ai/tasks/{task_id}").status_code == 200
        events = client.get(f"/api/ai/tasks/{task_id}/events?limit=1")
        assert events.status_code == 200
        assert events.json()["items"][0]["event_type"] == "TASK_CREATED"

        user_holder["value"] = _user("other")
        assert client.get(f"/api/ai/tasks/{task_id}").status_code == 404
        user_holder["value"] = _user()

        task = db.get(AITask, task_id)
        assert task is not None
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.UNDERSTOOD,
            actor_type="SYSTEM",
            reason_code="TASK_UNDERSTOOD",
            settings=_settings(),
        )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.PLANNED,
            actor_type="SYSTEM",
            reason_code="TASK_PLANNED",
            settings=_settings(),
        )
        db.commit()
        cancelled = client.post(
            f"/api/ai/tasks/{task_id}/cancel",
            json={"expected_revision": task.revision, "reason_code": "USER_CANCELLED"},
        )
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["state"] == "CANCELLING"

        second = client.post(
            "/api/ai/tasks",
            json=_payload(idempotency_key="api-task-owner-2").model_dump(mode="json"),
        )
        assert second.status_code == 201, second.text
        waiting = db.get(AITask, second.json()["id"])
        assert waiting is not None
        _advance_to_running(db, waiting)
        transition_task(
            db,
            task=waiting,
            requested_state=AITaskState.WAITING_INPUT,
            actor_type="SYSTEM",
            reason_code="TASK_WAITING_INPUT",
            settings=_settings(),
        )
        db.commit()
        resumed = client.post(
            f"/api/ai/tasks/{waiting.id}/resume",
            json={
                "expected_revision": waiting.revision,
                "expected_input_hash": waiting.input_hash,
                "expected_runtime_plan_hash": waiting.runtime_plan_hash,
            },
        )
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["state"] == "RUNNING"
        resumed_events = client.get(f"/api/ai/tasks/{waiting.id}/events")
        assert resumed_events.status_code == 200
        assert resumed_events.json()["items"][-1]["event_type"] == "RESUME_REQUESTED"
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_task_event_stream_recovers_cursor_restart_and_permission_change(
    monkeypatch,
) -> None:
    db = _database()
    live_user = {"value": _user()}

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: _user()
    monkeypatch.setattr(
        ai_tasks_api,
        "build_auth_context",
        lambda _db, _row: live_user["value"],
    )
    for name, value in (
        ("ai_enabled", True),
        ("ai_pilot_enabled", True),
        ("ai_pilot_user_ids", "owner,other"),
        ("ai_pilot_factory_ids", "huaxing"),
        ("ai_runtime_disable_path", ""),
        ("app_env", "development"),
        ("ai_nif_runtime_enabled", True),
        ("ai_skill_router_enabled", True),
        ("ai_evidence_v1_enabled", True),
        ("ai_tasks_enabled", True),
        ("ai_task_event_stream_poll_seconds", 0.01),
        ("ai_task_event_stream_max_seconds", 0.1),
    ):
        monkeypatch.setattr(settings, name, value)
    try:
        with TestClient(app) as first_client:
            created = first_client.post(
                "/api/ai/tasks",
                json=_payload(
                    idempotency_key="api-event-stream-owner-1"
                ).model_dump(mode="json"),
            )
            assert created.status_code == 201, created.text
            task_id = created.json()["id"]

        task = db.get(AITask, task_id)
        assert task is not None
        _advance_to_running(db, task)
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.VERIFYING,
            actor_type="SYSTEM",
            reason_code="TASK_VERIFYING",
            settings=_settings(),
        )
        transition_task(
            db,
            task=task,
            requested_state=AITaskState.COMPLETED,
            actor_type="SYSTEM",
            reason_code="TASK_COMPLETED",
            settings=_settings(),
        )
        db.commit()

        with TestClient(app) as restarted_client:
            listed = restarted_client.get("/api/ai/tasks")
            assert listed.status_code == 200, listed.text
            assert listed.json()["items"][0]["id"] == task_id
            recovered = restarted_client.get(
                f"/api/ai/tasks/{task_id}/events/stream",
                headers={"Last-Event-ID": "3"},
            )
            assert recovered.status_code == 200, recovered.text
            assert "id: 3" not in recovered.text
            assert "id: 4" in recovered.text
            assert "id: 5" in recovered.text
            assert "event: task.closed" in recovered.text

            live_user["value"] = _user("other")
            revoked = restarted_client.get(
                f"/api/ai/tasks/{task_id}/events/stream"
            )
            assert revoked.status_code == 200
            assert "event: task.error" in revoked.text
            assert "AI_TASK_NOT_FOUND" in revoked.text
    finally:
        app.dependency_overrides.clear()
        db.close()
