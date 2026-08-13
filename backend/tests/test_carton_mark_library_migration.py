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


def test_carton_mark_library_migration_upgrades_fresh_sqlite(tmp_path: Path) -> None:
    database_path = tmp_path / "carton-mark-library.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    result = _run_alembic(database_url, "upgrade", "head")
    assert result.returncode == 0, result.stderr

    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260813_0075",
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"carton_mark_templates", "carton_mark_documents"} <= tables
        document_foreign_keys = connection.execute(
            "PRAGMA foreign_key_list(carton_mark_documents)"
        ).fetchall()
        assert {row[2] for row in document_foreign_keys} == {"carton_mark_templates"}
        unique_index_columns = {
            tuple(
                column[2]
                for column in connection.execute(f"PRAGMA index_info('{row[1]}')")
            )
            for row in connection.execute("PRAGMA index_list(carton_mark_templates)")
            if row[2] == 1
        }
        assert ("factory_id", "document_fingerprint") in unique_index_columns
        assert (
            "factory_id",
            "business_key_sha256",
            "version",
        ) in unique_index_columns


def test_carton_mark_library_migration_refuses_data_loss_on_downgrade(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "carton-mark-library-populated.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgraded = _run_alembic(database_url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO carton_mark_templates (
                id, factory_id, customer_name, po, item, contract_number,
                business_key_sha256, document_fingerprint, version, check_status,
                check_result_json, excel_sha256, pdf_sha256, created_by,
                created_by_name, created_at, updated_at, is_archived,
                archived_by, archived_by_name, archived_at
            ) VALUES (
                'CMT-test', 'huaxing', '客户', 'PO-1', 'ITEM-1', 'C-1',
                :business_key, :fingerprint, 1, '核对通过', '{}', :excel_hash,
                :pdf_hash, 'user-test', '测试员', '2026-08-13T10:00:00',
                '2026-08-13T10:00:00', 0, '', '', ''
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

    rejected = _run_alembic(database_url, "downgrade", "20260813_0074")
    assert rejected.returncode != 0
    assert "cannot be downgraded after carton-mark data exists" in rejected.stderr
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260813_0075",
        )
