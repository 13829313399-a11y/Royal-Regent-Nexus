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


def test_carton_mark_customer_migration_creates_independent_library_and_backfills_templates(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "carton-mark-customers.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgraded_library = _run_alembic(database_url, "upgrade", "20260813_0075")
    assert upgraded_library.returncode == 0, upgraded_library.stderr

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
                'CMT-seed', 'huaxing', '  ZURU  ', 'PO-1', 'ITEM-1', 'C-1',
                :business_key, :fingerprint, 1, '核对通过', '{}', :excel_hash,
                :pdf_hash, 'user-test', '测试员', '2026-08-19T10:00:00',
                '2026-08-19T10:00:00', 0, '', '', ''
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

    upgraded = _run_alembic(database_url, "upgrade", "20260819_0080")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            "20260819_0080",
        )
        customer = connection.execute(
            "SELECT factory_id, name, normalized_name, revision "
            "FROM carton_mark_customers"
        ).fetchone()
        assert customer == ("huaxing", "ZURU", "zuru", 1)


def test_carton_mark_customer_migration_refuses_populated_downgrade(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "carton-mark-customers-populated.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    upgraded = _run_alembic(database_url, "upgrade", "20260819_0080")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO carton_mark_customers (
                id, factory_id, name, normalized_name, revision,
                created_by, created_by_name, created_at,
                updated_by, updated_by_name, updated_at
            ) VALUES (
                'CMC-test', 'huaxing', 'ZURU', 'zuru', 1,
                'user-test', '测试员', '2026-08-19T10:00:00',
                'user-test', '测试员', '2026-08-19T10:00:00'
            )
            """
        )
        connection.commit()

    rejected = _run_alembic(database_url, "downgrade", "20260818_0079")
    assert rejected.returncode != 0
    assert "cannot be downgraded after carton-mark customer data exists" in rejected.stderr
