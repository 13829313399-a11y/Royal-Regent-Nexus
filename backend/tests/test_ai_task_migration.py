from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND_DIR = Path(__file__).resolve().parents[1]


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


def test_ai_task_migration_upgrades_sqlite_with_single_head(tmp_path: Path) -> None:
    database_path = tmp_path / "ai-task.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = _run_alembic(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    assert {"ai_tasks", "ai_task_steps", "ai_task_events"} <= set(
        inspector.get_table_names()
    )
    task_columns = {item["name"] for item in inspector.get_columns("ai_tasks")}
    assert task_columns >= {
        "owner_user_id",
        "conversation_id",
        "factory_scope",
        "runtime_plan_json",
        "runtime_plan_hash",
        "tool_versions_json",
        "required_access_json",
        "input_hash",
        "idempotency_key",
        "next_event_sequence",
        "retention_expires_at",
        "backup_delete_by",
        "input_message_id",
        "lease_owner_instance",
        "lease_token",
        "lease_expires_at",
        "last_heartbeat_at",
        "next_attempt_at",
        "claim_count",
    }
    task_indexes = {item["name"]: item for item in inspector.get_indexes("ai_tasks")}
    assert task_indexes["uq_ai_task_owner_idempotency"]["unique"] == 1
    assert "ix_ai_task_worker_claim" in task_indexes
    step_columns = {
        item["name"] for item in inspector.get_columns("ai_task_steps")
    }
    assert step_columns >= {
        "arguments_json",
        "arguments_hash",
        "attempt_count",
        "max_attempts",
        "last_attempt_id",
        "last_attempt_started_at",
        "last_attempt_finished_at",
        "result_hash",
        "result_metadata_json",
    }
    event_indexes = {
        item["name"]: item for item in inspector.get_indexes("ai_task_events")
    }
    assert event_indexes["uq_ai_task_event_sequence"]["unique"] == 1
    task_checks = " ".join(
        str(item.get("sqltext", ""))
        for item in inspector.get_check_constraints("ai_tasks")
    )
    assert "WAITING_APPROVAL" in task_checks
    assert "PREVIEW_WITH_AUDIT" in task_checks
    step_checks = " ".join(
        str(item.get("sqltext", ""))
        for item in inspector.get_check_constraints("ai_task_steps")
    )
    assert "PREVIEW_STATE" in step_checks
    assert "max_attempts <= 3" in step_checks
    event_checks = " ".join(
        str(item.get("sqltext", ""))
        for item in inspector.get_check_constraints("ai_task_events")
    )
    assert "LEASE_CLAIMED" in event_checks
    assert "RETRY_SCHEDULED" in event_checks
    event_foreign_keys = {
        item["constrained_columns"][0]: item
        for item in inspector.get_foreign_keys("ai_task_events")
    }
    assert event_foreign_keys["task_id"]["options"].get("ondelete") == "CASCADE"
    assert event_foreign_keys["step_id"]["options"].get("ondelete") == "SET NULL"
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20260820_0080"
        )


def test_ai_task_downgrade_refuses_protected_data(tmp_path: Path) -> None:
    database_path = tmp_path / "protected-task.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    assert _run_alembic(database_url, "upgrade", "head").returncode == 0
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO auth_users "
                "(id, username, display_name, password_salt, password_hash, status, "
                "force_password_change, avatar_png, avatar_version, last_login_at, "
                "created_at, updated_at) VALUES "
                "('task-owner', 'task-owner', '', 'salt', 'hash', 'active', 0, NULL, "
                "'', '', '2026-08-12T08:00:00+08:00', '2026-08-12T08:00:00+08:00')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO ai_tasks "
                "(id, owner_user_id, factory_scope, task_type, state, maximum_risk, "
                "primary_skill_id, primary_skill_version, primary_skill_hash, "
                "prompt_version, prompt_hash, runtime_plan_json, runtime_plan_hash, "
                "input_hash, idempotency_key, request_hash, step_count, created_at, "
                "updated_at) VALUES "
                "(:id, 'task-owner', 'huaxing', 'READ', 'CREATED', 'READ_ONLY', "
                "'system.module_tutor', '1.0.0', :skill_hash, '1.0.0', :prompt_hash, "
                "'{}', :plan_hash, :input_hash, 'migration-task-1', :request_hash, 1, "
                "'2026-08-12T08:00:00+08:00', '2026-08-12T08:00:00+08:00')"
            ),
            {
                "id": "aitask-11111111111111111111111111111111",
                "skill_hash": "a" * 64,
                "prompt_hash": "b" * 64,
                "plan_hash": "c" * 64,
                "input_hash": "d" * 64,
                "request_hash": "e" * 64,
            },
        )
        connection.execute(
            sa.text(
                "UPDATE ai_tasks SET claim_count = 1 "
                "WHERE id = 'aitask-11111111111111111111111111111111'"
            )
        )

    result = _run_alembic(database_url, "downgrade", "20260813_0068")
    assert result.returncode != 0
    assert "Refusing to downgrade 20260813_0070" in result.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20260813_0070"
        )
        assert (
            connection.execute(sa.text("SELECT COUNT(*) FROM ai_tasks")).scalar_one()
            == 1
        )


def test_empty_ai_task_migration_can_downgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "empty-task.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    assert _run_alembic(database_url, "upgrade", "head").returncode == 0
    result = _run_alembic(database_url, "downgrade", "20260813_0068")
    assert result.returncode == 0, result.stderr
    engine = sa.create_engine(database_url)
    assert "ai_tasks" not in sa.inspect(engine).get_table_names()
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20260813_0068"
        )


def test_ai_task_migration_renders_postgresql_semantics() -> None:
    result = _run_alembic(
        "postgresql+psycopg://postgres:postgres@localhost:5432/rr",
        "upgrade",
        "20260813_0068:20260813_0070",
        "--sql",
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE ai_tasks" in result.stdout
    assert "CREATE TABLE ai_task_steps" in result.stdout
    assert "CREATE TABLE ai_task_events" in result.stdout
    assert "ON DELETE RESTRICT" in result.stdout
    assert "ON DELETE CASCADE" in result.stdout
    assert "ON DELETE SET NULL" in result.stdout
    assert "uq_ai_task_event_sequence" in result.stdout
    assert "WAITING_APPROVAL" in result.stdout
    assert "PREVIEW_STATE" in result.stdout
    assert "lease_owner_instance" in result.stdout
    assert "ix_ai_task_worker_claim" in result.stdout
    assert "arguments_json" in result.stdout
    assert "LEASE_CLAIMED" in result.stdout
