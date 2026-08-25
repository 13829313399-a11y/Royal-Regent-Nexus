from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_alembic(
    database_url: str,
    *arguments: str,
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


def test_ai_guard_migration_has_metadata_only_tables_and_single_head(tmp_path):
    database_path = tmp_path / "ai-guard.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = _run_alembic(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    assert {
        "ai_guard_leases",
        "ai_guard_request_events",
        "ai_guard_daily_budgets",
        "ai_guard_disable_states",
    } <= set(inspector.get_table_names())
    all_columns = {
        column["name"]
        for table_name in (
            "ai_guard_leases",
            "ai_guard_request_events",
            "ai_guard_daily_budgets",
            "ai_guard_disable_states",
        )
        for column in inspector.get_columns(table_name)
    }
    assert not {
        "prompt",
        "prompt_text",
        "business_payload",
        "tool_result",
        "message_body",
    }.intersection(all_columns)
    assert {
        "lease_token",
        "instance_id",
        "reservation_tokens",
        "budget_day",
        "expires_at",
    } <= {
        column["name"]
        for column in inspector.get_columns("ai_guard_leases")
    }
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260821_0082"


def test_ai_guard_migration_refuses_downgrade_with_shared_state(tmp_path):
    database_path = tmp_path / "ai-guard-protected.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    assert _run_alembic(database_url, "upgrade", "head").returncode == 0
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO ai_guard_disable_states "
                "(scope_type, scope_id, disabled, reason_code, expires_at, "
                "updated_by_instance, updated_at) VALUES "
                "('GLOBAL', '*', 1, 'TEST', '', 'ops:test', "
                "'2026-08-12T08:00:00Z')"
            )
        )
    result = _run_alembic(database_url, "downgrade", "20260813_0070")
    assert result.returncode != 0
    assert "Refusing to downgrade 20260813_0071" in result.stderr
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260813_0071"


def test_ai_guard_migration_renders_postgresql_contract():
    result = _run_alembic(
        "postgresql+psycopg://postgres:postgres@localhost:5432/rr",
        "upgrade",
        "20260813_0070:20260813_0071",
        "--sql",
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE ai_guard_leases" in result.stdout
    assert "CREATE TABLE ai_guard_request_events" in result.stdout
    assert "CREATE TABLE ai_guard_daily_budgets" in result.stdout
    assert "CREATE TABLE ai_guard_disable_states" in result.stdout
