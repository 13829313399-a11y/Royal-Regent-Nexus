import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa
from app.models.ai_action import AIActionConfirmation
from app.models.auth import AuthUser
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _user() -> AuthUser:
    return AuthUser(
        id="action-migration-user",
        username="action-migration-user",
        display_name="Action Migration User",
        password_salt="salt",
        password_hash="hash",
        status="active",
        force_password_change=0,
        avatar_png=None,
        avatar_version="",
        last_login_at="",
        created_at="2026-08-13T08:00:00+08:00",
        updated_at="2026-08-13T08:00:00+08:00",
    )


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
        "gateway_contract_version",
        "action_type",
        "handler_version",
        "approval_policy_version",
        "lifecycle_status",
        "approval_user_id",
        "approval_request_id",
        "approval_args_hash",
        "approval_entity_revision",
        "approval_expires_at",
        "execution_user_id",
        "domain_audit_id",
        "verification_result_json",
        "compensation_json",
    }
    indexes = {item["name"]: item for item in inspector.get_indexes("ai_action_confirmations")}
    assert indexes["uq_ai_action_confirmation_request"]["unique"] == 1
    assert indexes["uq_ai_action_confirmation_execution_request"]["unique"] == 1
    assert indexes["uq_ai_action_approval_request"]["unique"] == 1
    checks = " ".join(
        str(item.get("sqltext", ""))
        for item in inspector.get_check_constraints("ai_action_confirmations")
    )
    assert "PENDING" in checks
    assert "PROPOSED" in checks
    assert "WAITING_APPROVAL" in checks
    assert "CONSEQUENTIAL_WRITE" in checks
    with engine.connect() as connection:
        assert connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one() == (
            "20260813_0075"
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


def test_ai_action_gateway_migration_renders_postgresql_ddl() -> None:
    result = _run_alembic(
        "postgresql+psycopg://postgres:postgres@localhost:5432/rr",
        "upgrade",
        "20260813_0073:20260813_0074",
        "--sql",
    )
    assert result.returncode == 0, result.stderr
    assert "lifecycle_status" in result.stdout
    assert "approval_request_id" in result.stdout
    assert "verification_result_json" in result.stdout
    assert "uq_ai_action_approval_request" in result.stdout
    assert "PROPOSED" in result.stdout
    assert "WAITING_APPROVAL" in result.stdout


def test_action_gateway_migration_backfills_legacy_record_and_can_downgrade(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ai-action-legacy.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    initial = _run_alembic(database_url, "upgrade", "20260812_0066")
    assert initial.returncode == 0, initial.stderr
    engine = sa.create_engine(database_url)
    with Session(engine) as db:
        db.add(_user())
        db.commit()
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO ai_action_confirmations ("
                "id, user_id, tool_name, risk_level, factory_id, entity_type, "
                "entity_id, entity_revision, args_hash, normalized_action_json, "
                "request_id, expires_at, status, created_at) VALUES ("
                "'aic-legacy', 'action-migration-user', "
                "'injection_scheduling.apply_preview_run', 'CONSEQUENTIAL_WRITE', "
                "'huaxing', 'auto_schedule_run', 'legacy-run', 1, :hash, '{}', "
                "'legacy-request', '2026-08-13T09:00:00+08:00', 'CONFIRMED', "
                "'2026-08-13T08:00:00+08:00')"
            ),
            {"hash": "a" * 64},
        )
    upgraded = _run_alembic(database_url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                "SELECT gateway_contract_version, lifecycle_status, "
                "approval_user_id, approval_args_hash FROM "
                "ai_action_confirmations WHERE id = 'aic-legacy'"
            )
        ).one()
        assert tuple(row) == (
            "legacy-confirmation-v1",
            "APPROVED",
            "action-migration-user",
            "a" * 64,
        )
    downgraded = _run_alembic(database_url, "downgrade", "20260813_0073")
    assert downgraded.returncode == 0, downgraded.stderr


def test_action_gateway_migration_refuses_to_drop_gateway_evidence(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "ai-action-protected.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgraded = _run_alembic(database_url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    engine = sa.create_engine(database_url)
    with Session(engine) as db:
        db.add(_user())
        db.flush()
        db.add(
            AIActionConfirmation(
                id="aic-protected",
                user_id="action-migration-user",
                tool_name="injection_scheduling.apply_preview_run",
                risk_level="CONSEQUENTIAL_WRITE",
                factory_id="huaxing",
                entity_type="auto_schedule_run",
                entity_id="protected-run",
                entity_revision=1,
                args_hash="b" * 64,
                normalized_action_json="{}",
                request_id="protected-request",
                expires_at="2026-08-13T09:00:00+08:00",
                status="PENDING",
                created_at="2026-08-13T08:00:00+08:00",
                gateway_contract_version="action-gateway-v1",
                action_type="APPLY_INJECTION_AUTO_SCHEDULE_RUN",
                handler_version="1.0.0",
                approval_policy_version="1.0.0",
                lifecycle_status="WAITING_APPROVAL",
            )
        )
        db.commit()
    downgrade = _run_alembic(database_url, "downgrade", "20260813_0073")
    assert downgrade.returncode != 0
    assert "Refusing to downgrade 20260813_0074" in downgrade.stderr
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            == "20260813_0074"
        )
