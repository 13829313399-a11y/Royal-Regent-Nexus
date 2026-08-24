import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

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


def test_qc_inspection_migration_upgrades_fresh_sqlite_and_seeds_permissions(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "qc-inspection.db"
    result = _run_alembic(
        f"sqlite:///{database_path.as_posix()}",
        "upgrade",
        "head",
    )
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260824_0082",
        )
        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert {
            "qc_inspection_events",
            "qc_inspection_event_lines",
            "qc_inspection_defects",
            "qc_inspection_test_results",
            "qc_inspection_dispositions",
            "qc_inspection_report_packages",
            "qc_inspection_report_documents",
        } <= table_names
        qc_permissions = connection.execute(
            "SELECT COUNT(*) FROM auth_permissions WHERE code LIKE 'qc_inspection:%'"
        ).fetchone()
        assert qc_permissions == (12,)
        group_summary = connection.execute(
            """
            SELECT metadata.access_kind, metadata.risk_level, metadata.scope_type
            FROM auth_permission_metadata metadata
            JOIN auth_permissions permission ON permission.id = metadata.permission_id
            WHERE permission.code = 'qc_inspection:group_summary'
            """
        ).fetchone()
        assert group_summary == ("operate", "high", "factory_department")


def test_qc_inspection_migration_renders_literal_postgresql_permission_seed() -> None:
    result = _run_alembic(
        "postgresql+psycopg://postgres:postgres@localhost:5432/rr",
        "upgrade",
        "20260812_0066:20260812_0067",
        "--sql",
    )
    assert result.returncode == 0, result.stderr

    output = result.stdout
    seed_start = output.index("INSERT INTO auth_permissions")
    seed_end = output.index("UPDATE alembic_version", seed_start)
    seed_sql = output[seed_start:seed_end]
    assert "qc_inspection:group_summary" in seed_sql
    assert "perm-qc_inspection-group_summary" in seed_sql
    assert "position_qc_inspector" in seed_sql
    assert "position_qc_supervisor" in seed_sql
    assert "position_qc_manager" in seed_sql
    assert re.search(r"\bNULL\b", seed_sql, flags=re.IGNORECASE) is None
