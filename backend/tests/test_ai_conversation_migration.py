from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
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


def test_ai_conversation_migration_upgrades_sqlite_with_single_head(tmp_path: Path) -> None:
    database_path = tmp_path / "ai-conversation.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = _run_alembic(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    assert {
        "ai_conversations",
        "ai_messages",
        "ai_conversation_summaries",
        "ai_conversation_context_bindings",
    } <= set(inspector.get_table_names())
    conversation_columns = {
        item["name"] for item in inspector.get_columns("ai_conversations")
    }
    assert conversation_columns >= {
        "id",
        "owner_user_id",
        "factory_scope",
        "mode",
        "status",
        "title",
        "revision",
        "message_count",
        "next_message_ordinal",
        "expires_at",
        "title_expires_at",
        "deleted_at",
        "tombstone_expires_at",
        "last_idempotency_key",
        "last_request_hash",
        "last_ephemeral_message_id",
        "pinned_at",
        "archived_at",
    }
    message_indexes = {
        item["name"]: item for item in inspector.get_indexes("ai_messages")
    }
    assert message_indexes["uq_ai_message_conversation_ordinal"]["unique"] == 1
    assert message_indexes["uq_ai_message_idempotency"]["unique"] == 1
    message_checks = " ".join(
        str(item.get("sqltext", ""))
        for item in inspector.get_check_constraints("ai_messages")
    )
    assert "CONVERSATIONAL_ONLY" in message_checks
    assert "ASSISTANT" in message_checks
    foreign_keys = inspector.get_foreign_keys("ai_messages")
    assert foreign_keys[0]["referred_table"] == "ai_conversations"
    assert foreign_keys[0]["options"].get("ondelete") == "CASCADE"
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == ("20260820_0080")


def test_ai_conversation_downgrade_refuses_protected_data(tmp_path: Path) -> None:
    database_path = tmp_path / "protected-conversation.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = _run_alembic(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO auth_users "
                "(id, username, display_name, password_salt, password_hash, status, "
                "force_password_change, avatar_png, avatar_version, last_login_at, "
                "created_at, updated_at) VALUES "
                "('migration-owner', 'migration-owner', '', 'salt', 'hash', 'active', "
                "0, NULL, '', '', '2026-08-12T08:00:00+08:00', "
                "'2026-08-12T08:00:00+08:00')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO ai_conversations "
                "(id, owner_user_id, factory_scope, mode, status, title, revision, "
                "message_count, next_message_ordinal, created_at, updated_at) VALUES "
                "('aicv-11111111111111111111111111111111', 'migration-owner', "
                "'huaxing', 'PERSISTENT', 'ACTIVE', 'protected', 1, 0, 1, "
                "'2026-08-12T08:00:00+08:00', '2026-08-12T08:00:00+08:00')"
            )
        )

    result = _run_alembic(database_url, "downgrade", "20260812_0066")
    assert result.returncode != 0
    assert "Refusing to downgrade 20260813_0068" in result.stderr
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == ("20260813_0068")
        assert connection.execute(
            sa.text("SELECT COUNT(*) FROM ai_conversations")
        ).scalar_one() == 1


def test_empty_ai_conversation_migration_can_downgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "empty-conversation.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    assert _run_alembic(database_url, "upgrade", "head").returncode == 0
    result = _run_alembic(database_url, "downgrade", "20260812_0066")
    assert result.returncode == 0, result.stderr
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    assert "ai_conversations" not in inspector.get_table_names()
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == ("20260812_0066")


def test_ai_conversation_migration_renders_postgresql_semantics() -> None:
    result = _run_alembic(
        "postgresql+psycopg://postgres:postgres@localhost:5432/rr",
        "upgrade",
        "20260812_0067:20260813_0068",
        "--sql",
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE ai_conversations" in result.stdout
    assert "CREATE TABLE ai_messages" in result.stdout
    assert "CREATE TABLE ai_conversation_summaries" in result.stdout
    assert "ON DELETE CASCADE" in result.stdout
    assert "uq_ai_message_idempotency" in result.stdout
    assert "idempotency_key != ''" in result.stdout
    assert "CONVERSATIONAL_ONLY" in result.stdout
