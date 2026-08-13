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


def test_ai_action_confirmation_migration_upgrades_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "ai-action-confirmation.db"
    result = _run_alembic(
        f"sqlite:///{database_path.as_posix()}",
        "upgrade",
        "head",
    )
    assert result.returncode == 0, result.stderr

    engine = sa.create_engine(f"sqlite:///{database_path.as_posix()}")
    inspector = sa.inspect(engine)
    columns = {item["name"] for item in inspector.get_columns("ai_action_confirmations")}
    assert columns >= {
        "id",
        "user_id",
        "tool_name",
        "risk_level",
        "factory_id",
        "entity_type",
        "entity_id",
        "entity_revision",
        "args_hash",
        "normalized_action_json",
        "request_id",
        "expires_at",
        "status",
        "created_at",
        "confirmed_at",
        "executed_at",
        "execution_request_id",
        "execution_result_json",
        "failure_code",
    }
    indexes = {item["name"]: item for item in inspector.get_indexes("ai_action_confirmations")}
    assert indexes["uq_ai_action_confirmation_request"]["unique"] == 1
    assert indexes["uq_ai_action_confirmation_execution_request"]["unique"] == 1
    checks = " ".join(
        str(item.get("sqltext", ""))
        for item in inspector.get_check_constraints("ai_action_confirmations")
    )
    assert "PENDING" in checks
    assert "CONSEQUENTIAL_WRITE" in checks
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "20260812_0067"
        )


def test_ai_action_confirmation_migration_renders_postgresql_ddl() -> None:
    result = _run_alembic(
        "postgresql+psycopg://postgres:postgres@localhost:5432/rr",
        "upgrade",
        "20260811_0065:20260812_0066",
        "--sql",
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE ai_action_confirmations" in result.stdout
    assert "uq_ai_action_confirmation_execution_request" in result.stdout
    assert "execution_request_id != ''" in result.stdout
    assert "CONSEQUENTIAL_WRITE" in result.stdout
