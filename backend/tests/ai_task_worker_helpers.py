from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.db import Base
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.ai_task import AITask, AITaskEvent, AITaskStep
from app.models.auth import AuthAuditLog, AuthUser
from app.schemas.ai.task import AITaskCreate, AITaskStepCreate, AITaskType
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.task_service import create_task
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.auth import AuthContext, AuthGrantContext

FAKE_TASK_SKILL_ROOT = Path(__file__).resolve().parent / "fixtures" / "ai_task_skill"


def worker_settings(database_url: str = "sqlite://") -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        ai_enabled=True,
        ai_provider="fake",
        ai_provider_capability_router_enabled=False,
        ai_nif_runtime_enabled=True,
        ai_skill_router_enabled=True,
        ai_evidence_v1_enabled=True,
        ai_tasks_enabled=True,
        ai_task_worker_enabled=True,
        ai_pilot_enabled=True,
        ai_pilot_user_ids="owner",
        ai_pilot_factory_ids="huaxing",
    )


def worker_user() -> AuthContext:
    grant = AuthGrantContext(
        role_id="worker-test",
        role_name="Worker Test",
        role_code="worker-test",
        factory_id="huaxing",
        department="production",
        permissions=frozenset(),
        binding_id="worker-test-binding",
    )
    return AuthContext(
        id="owner",
        username="owner",
        display_name="Owner",
        roles=("Worker Test",),
        role_codes=("worker-test",),
        permissions=frozenset(),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=(grant,),
    )


def _enable_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _pragma(connection, _record) -> None:
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def worker_database(database_url: str = "sqlite://") -> sessionmaker[Session]:
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )
    _enable_foreign_keys(engine)
    Base.metadata.create_all(
        engine,
        tables=[
            AuthUser.__table__,
            AuthAuditLog.__table__,
            AIConversation.__table__,
            AIMessage.__table__,
            AITask.__table__,
            AITaskStep.__table__,
            AITaskEvent.__table__,
        ],
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as db:
        db.add(
            AuthUser(
                id="owner",
                username="owner",
                display_name="Owner",
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
    return factory


def compute_payload(key: str = "worker-compute-task-1") -> AITaskCreate:
    return AITaskCreate(
        task_type=AITaskType.COMPUTE,
        factory_scope="huaxing",
        primary_skill_id="system.module_tutor",
        proposed_tool_names=(),
        proposed_max_steps=1,
        input_hash="a" * 64,
        idempotency_key=key,
        steps=(
            AITaskStepCreate(
                key="compute_answer",
                kind=AITaskType.COMPUTE,
                label="生成有界回答",
            ),
        ),
    )


def fake_task_payload(key: str = "worker-fake-skill-task-1") -> AITaskCreate:
    return AITaskCreate(
        task_type=AITaskType.COMPUTE,
        factory_scope="huaxing",
        primary_skill_id="test.fake_task",
        proposed_tool_names=(),
        proposed_max_steps=1,
        input_hash="c" * 64,
        idempotency_key=key,
        steps=(
            AITaskStepCreate(
                key="fake_compute",
                kind=AITaskType.COMPUTE,
                label="执行测试专用 Fake Task Skill",
            ),
        ),
    )


def fake_task_skill_registry(tool_registry) -> SkillRegistry:
    return SkillRegistry(
        tool_registry,
        manifest_root=FAKE_TASK_SKILL_ROOT / "manifests",
        prompt_registry=PromptRegistry(prompt_root=FAKE_TASK_SKILL_ROOT / "prompts"),
    )


def tool_payload(key: str = "worker-tool-task-1") -> AITaskCreate:
    return AITaskCreate(
        task_type=AITaskType.READ,
        factory_scope="huaxing",
        primary_skill_id="system.module_tutor",
        proposed_tool_names=("identity.get_current_context",),
        proposed_max_steps=1,
        input_hash="b" * 64,
        idempotency_key=key,
        steps=(
            AITaskStepCreate(
                key="read_context",
                kind=AITaskType.READ,
                label="读取身份上下文",
                tool_name="identity.get_current_context",
                arguments={},
            ),
        ),
    )


def create_worker_task(
    factory: Callable[[], Session],
    *,
    payload: AITaskCreate | None = None,
    settings: Settings | None = None,
    skill_registry: SkillRegistry | None = None,
) -> str:
    config = settings or worker_settings()
    registry = build_default_tool_registry(controlled_apply_enabled=False)
    with factory() as db:
        task = create_task(
            db,
            payload=payload or compute_payload(),
            user=worker_user(),
            settings=config,
            registry=registry,
            skill_registry=skill_registry or SkillRegistry(registry),
            server_page_context=None,
            allowed_factory_scopes=frozenset({"huaxing"}),
            request_id="worker-test-request",
        )
        return task.id


def worker_auth_loader(_db: Session, _task: AITask, _settings: Settings) -> AuthContext:
    return worker_user()
