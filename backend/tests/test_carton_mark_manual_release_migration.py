import os
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


def test_manual_release_migration_adds_fields_on_fresh_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "carton-mark-manual-release.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = _run_alembic(database_url, "upgrade", "20260825_0083")
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260825_0083",
        )
        columns = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(carton_mark_templates)")
        }
        assert {
            "manual_release_reason",
            "manual_release_source_status",
            "manual_released_by",
            "manual_released_by_name",
            "manual_released_at",
        } <= columns.keys()
        assert all(columns[name][3] == 1 for name in (
            "manual_release_reason",
            "manual_release_source_status",
            "manual_released_by",
            "manual_released_by_name",
            "manual_released_at",
        ))


def test_manual_release_migration_refuses_to_drop_approval_evidence(tmp_path: Path) -> None:
    database_path = tmp_path / "carton-mark-manual-release-populated.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgraded = _run_alembic(database_url, "upgrade", "20260825_0083")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO carton_mark_templates (
                id, factory_id, customer_name, po, item, contract_number,
                business_key_sha256, document_fingerprint, version, check_status,
                check_result_json, excel_sha256, pdf_sha256, created_by,
                created_by_name, created_at, updated_at, is_archived,
                archived_by, archived_by_name, archived_at,
                manual_release_reason, manual_release_source_status,
                manual_released_by, manual_released_by_name, manual_released_at
            ) VALUES (
                'CMT-manual', 'huaxing', '客户', 'PO-1', 'ITEM-1', 'C-1',
                :business_key, :fingerprint, 1, '发现差异', '{}', :excel_hash,
                :pdf_hash, 'user-test', '测试员', '2026-08-25T10:00:00',
                '2026-08-25T10:00:00', 0, '', '', '',
                '客户书面确认差异可接受', '发现差异', 'reviewer', '纸箱主管',
                '2026-08-25T11:00:00'
            )
            """,
            {
                "business_key": "a" * 64,
                "fingerprint": "b" * 64,
                "excel_hash": "c" * 64,
                "pdf_hash": "d" * 64,
            },
        )
        connection.commit()

    rejected = _run_alembic(database_url, "downgrade", "20260824_0082")
    assert rejected.returncode != 0
    assert "拒绝降级以避免丢失审批证据" in rejected.stderr
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260825_0083",
        )
