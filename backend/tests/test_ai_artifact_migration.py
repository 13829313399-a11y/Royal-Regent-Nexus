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


def test_ai_artifact_migration_contract_and_single_head(tmp_path) -> None:
    database_path = tmp_path / "ai-artifacts.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = _run_alembic(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    engine = sa.create_engine(database_url)
    inspector = sa.inspect(engine)
    assert "ai_artifacts" in inspector.get_table_names()
    columns = {item["name"] for item in inspector.get_columns("ai_artifacts")}
    assert {
        "id",
        "owner_user_id",
        "factory_id",
        "original_filename",
        "normalized_extension",
        "declared_mime_type",
        "detected_mime_type",
        "content_class",
        "size_bytes",
        "sha256",
        "classification",
        "storage_key",
        "scanner_status",
        "parser_status",
        "parent_artifact_id",
        "derivation_type",
        "retention_until",
        "deleted_at",
        "created_at",
    } <= columns
    check_names = {item["name"] for item in inspector.get_check_constraints("ai_artifacts")}
    assert {
        "ck_ai_artifact_classification",
        "ck_ai_artifact_status",
        "ck_ai_artifact_lineage",
    } <= check_names
    index_names = {item["name"] for item in inspector.get_indexes("ai_artifacts")}
    assert {
        "ix_ai_artifact_owner_status",
        "ix_ai_artifact_factory_status",
        "ix_ai_artifact_retention",
        "ix_ai_artifact_sha256",
    } <= index_names
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260820_0080"


def test_ai_artifact_migration_refuses_downgrade_with_data(tmp_path) -> None:
    database_path = tmp_path / "ai-artifacts-protected.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    assert _run_alembic(database_url, "upgrade", "head").returncode == 0
    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO ai_artifacts (id, owner_user_id, factory_id, "
                "original_filename, normalized_extension, declared_mime_type, "
                "detected_mime_type, content_class, size_bytes, sha256, "
                "classification, storage_key, status, scanner_status, "
                "scanner_result_code, parser_status, parser_version, model_version, "
                "parent_artifact_id, derivation_type, retention_until, deleted_at, "
                "storage_deleted_at, tombstone_expires_at, backup_delete_by, "
                "created_at, updated_at) VALUES "
                "('aiart-00000000000000000000000000000000', 'admin', 'huaxing', "
                "'test.csv', '.csv', 'text/csv', 'text/csv', 'WORKBOOK', 1, "
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                "'INTERNAL', 'v1/00/aiart-00000000000000000000000000000000.bin', "
                "'ACTIVE', 'CLEAN', 'CLEAN', 'NOT_REQUESTED', '', '', NULL, "
                "'ORIGINAL', '2026-09-11T10:00:00+08:00', '', '', '', '', "
                "'2026-08-12T10:00:00+08:00', '2026-08-12T10:00:00+08:00')"
            )
        )
    result = _run_alembic(database_url, "downgrade", "20260813_0071")
    assert result.returncode != 0
    assert "Refusing to downgrade 20260813_0072" in result.stderr
    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20260813_0072"


def test_ai_artifact_migration_renders_postgresql_contract() -> None:
    result = _run_alembic(
        "postgresql+psycopg://postgres:postgres@localhost:5432/rr",
        "upgrade",
        "20260813_0071:20260813_0072",
        "--sql",
    )
    assert result.returncode == 0, result.stderr
    assert "CREATE TABLE ai_artifacts" in result.stdout
    assert "FOREIGN KEY(parent_artifact_id)" in result.stdout
    assert "ck_ai_artifact_classification" in result.stdout
    assert "ix_ai_artifact_retention" in result.stdout
