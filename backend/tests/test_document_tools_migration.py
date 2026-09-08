"""Verify both independently developed schema branches reach one usable head."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

BACKEND = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("starting_revision", ["20260907_0102", "20260908_0104", "20260908_0103_docs"])
def test_both_schema_branches_upgrade_without_losing_document_tables(tmp_path, starting_revision):
    database = tmp_path / "merge.db"
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{database.as_posix()}")

    def upgrade(target):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", target],
            cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0, result.stderr

    upgrade(starting_revision)
    with sqlite3.connect(database) as connection:
        previous = dict(connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name LIKE 'document_tool_%'"))
    upgrade("head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [("20260908_0105",)]
        tables = dict(connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"))
        assert {"document_tool_sources", "document_tool_jobs", "document_tool_artifacts", "document_tool_corrections", "carton_locations", "carton_position_entries", "carton_master_records", "carton_master_sources"} <= tables.keys()
        assert all(tables[name] == sql for name, sql in previous.items())
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
