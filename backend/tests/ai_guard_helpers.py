from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.models.ai_guard import (
    AIGuardDailyBudget,
    AIGuardDisableState,
    AIGuardLease,
    AIGuardRequestEvent,
)
from app.services.ai.pilot_guard import AIPilotGuard
from app.services.ai.postgres_guard_backend import PostgreSQLGuardBackend
from app.services.auth import AuthContext


def shared_settings(**overrides) -> Settings:
    values = {
        "app_env": "development",
        "ai_enabled": True,
        "ai_provider": "qwen",
        "ai_region": "cn-beijing",
        "ai_workspace_id": "ws-shared-guard-test",
        "dashscope_api_key": "synthetic-test-key",
        "ai_default_model": "qwen3.7-plus",
        "ai_pilot_enabled": True,
        "ai_pilot_user_ids": "user-pilot",
        "ai_pilot_factory_ids": "huaxing",
        "ai_runtime_disable_path": "",
        "ai_shared_guard_enabled": True,
        "ai_guard_lease_seconds": 180,
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


def pilot_user(
    *,
    user_id: str = "user-pilot",
    factory_scopes: tuple[str, ...] = ("huaxing",),
) -> AuthContext:
    return AuthContext(
        id=user_id,
        username=user_id,
        display_name="共享 Guard 测试用户",
        roles=("测试",),
        role_codes=("test",),
        permissions=frozenset(),
        factory_scopes=factory_scopes,
        department_scopes=(),
    )


@pytest.fixture
def shared_guard_runtime(tmp_path: Path) -> Iterator[tuple[object, object, object]]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'shared-guard.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 10},
        future=True,
    )
    for table in (
        AIGuardLease.__table__,
        AIGuardRequestEvent.__table__,
        AIGuardDailyBudget.__table__,
        AIGuardDisableState.__table__,
    ):
        table.create(engine)
    sessions = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )
    backend = PostgreSQLGuardBackend(sessions, allow_sqlite_for_tests=True)
    try:
        yield backend, sessions, engine
    finally:
        engine.dispose()


def shared_guard(
    backend,
    *,
    instance_id: str,
    current: list[datetime] | None = None,
) -> AIPilotGuard:
    now = current or [datetime(2026, 8, 12, 8, 0, tzinfo=UTC)]
    return AIPilotGuard(
        utcnow=lambda: now[0],
        shared_backend=backend,
        instance_id=instance_id,
    )
